import { createElement, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth0 } from '@auth0/auth0-react';
import {
  getTwelvelabsHistory,
  getTwelvelabsIndexVideos,
  getAgentDecision,
  getDecisionExplanation,
  getCloudinaryEvents,
  getCloudinaryLatest,
  runCloudinaryLocalAnalyze,
  ingestVideoToTwelvelabs,
  askIndexedVideoQuestion,
  mapSensorsToApi,
  summarizeIndexedVideo,
  type CloudinaryEventRowApi,
  type CloudinaryLatestResponseApi,
  type CropStage,
  type DecisionResponseApi,
  type TwelvelabsHistoryItemApi,
  type TwelvelabsIndexVideoApi,
  type TwelvelabsIngestionResultApi,
} from './api/agriApi';
import { uploadPreset } from './cloudinary/config';
import { UploadWidget } from './cloudinary/UploadWidget';
import type { CloudinaryUploadResult } from './cloudinary/UploadWidget';
import './App.css';

interface SensorSnapshot {
  soilMoisture: number;
  temperatureC: number;
  humidity: number;
  lightLux: number;
  ph: number;
}

interface DiagnosisResult {
  label: string;
  confidence: number;
  urgency: 'low' | 'medium' | 'high';
  actions: string[];
}

interface ParsedFarmSegment {
  startLabel: string;
  endLabel: string;
  title: string;
  startSec: number;
  endSec: number;
}

type ChatRole = 'user' | 'agent';

interface IrrigatorChatMessage {
  role: ChatRole;
  text: string;
}

interface IrrigatorFormState {
  city: string;
  latitude: string;
  longitude: string;
  temperature: number;
  moisture: number;
  light: number;
  airQuality: number;
}

interface IrrigatorResult {
  rainExpected: boolean;
  weatherSummary: string;
  waterNeed: number;
  action: 'water' | 'skip';
  amountMl: number;
  reason: string;
}

interface SensorTrendPoint {
  label: string;
  temperatureC: number;
  airQuality: number;
  moisture: number;
  lightLux: number;
}

type TrendMetricKey = 'temperatureC' | 'airQuality' | 'moisture' | 'lightLux';
interface DiseasePredictionItem {
  rank: number;
  label: string;
  confidence: number;
}

type AppPage = 'dashboard' | 'twelvelabs' | 'cloudinary' | 'diseaseAnalysis' | 'irrigator';
type AppRoute = 'landing' | 'auth' | AppPage;

interface AppProps {
  authEnabled?: boolean;
}

const hasUploadPreset = Boolean(uploadPreset);
const INITIAL_SENSORS: SensorSnapshot = {
  soilMoisture: 46,
  temperatureC: 28,
  humidity: 63,
  lightLux: 12000,
  ph: 6.7,
};
const INITIAL_IRRIGATOR_FORM: IrrigatorFormState = {
  city: 'Toronto',
  latitude: '',
  longitude: '',
  temperature: 30,
  moisture: 28,
  light: 900,
  airQuality: 72,
};
const SENSOR_TREND_DATA: SensorTrendPoint[] = [
  { label: '06:00', temperatureC: 22, airQuality: 79, moisture: 58, lightLux: 1800 },
  { label: '08:00', temperatureC: 24, airQuality: 76, moisture: 56, lightLux: 5200 },
  { label: '10:00', temperatureC: 27, airQuality: 73, moisture: 53, lightLux: 12000 },
  { label: '12:00', temperatureC: 31, airQuality: 68, moisture: 49, lightLux: 19500 },
  { label: '14:00', temperatureC: 33, airQuality: 65, moisture: 46, lightLux: 23400 },
  { label: '16:00', temperatureC: 30, airQuality: 69, moisture: 44, lightLux: 20100 },
  { label: '18:00', temperatureC: 27, airQuality: 74, moisture: 45, lightLux: 11800 },
  { label: '20:00', temperatureC: 24, airQuality: 78, moisture: 47, lightLux: 3200 },
];
const TREND_REFRESH_MS = 2500;
const TREND_POINT_LIMIT = 24;
const LANDING_TAGLINE = 'Smart farming intelligence';
const LANDING_HEADING = 'AgriMind powers better farm decisions.';

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function getHealthStatus(sensors: SensorSnapshot): string {
  if (sensors.soilMoisture < 30) return 'Water stress risk';
  if (sensors.temperatureC > 35) return 'Heat stress risk';
  if (sensors.lightLux < 5000) return 'Low-light growth risk';
  if (sensors.ph < 5.8 || sensors.ph > 7.4) return 'Soil pH correction needed';
  return 'Conditions stable';
}

function scoreHealth(sensors: SensorSnapshot): number {
  const moisturePenalty = Math.abs(50 - sensors.soilMoisture) * 0.9;
  const temperaturePenalty = Math.abs(26 - sensors.temperatureC) * 1.4;
  const humidityPenalty = Math.abs(60 - sensors.humidity) * 0.5;
  const lightPenalty = sensors.lightLux < 8000 ? (8000 - sensors.lightLux) / 1200 : 0;
  const phPenalty = Math.abs(6.6 - sensors.ph) * 12;

  const rawScore = 100 - (moisturePenalty + temperaturePenalty + humidityPenalty + lightPenalty + phPenalty);
  return Math.round(clamp(rawScore, 35, 99));
}

function runLeafDiagnosis(result: CloudinaryUploadResult): DiagnosisResult {
  const id = result.public_id.toLowerCase();
  const format = result.format.toLowerCase();
  const hashHint = result.bytes % 17;
  const confidenceBase = 62 + (hashHint % 18);

  if (id.includes('spot') || id.includes('blight')) {
    return {
      label: 'Possible fungal leaf spot',
      confidence: clamp(confidenceBase + 14, 70, 95),
      urgency: 'high',
      actions: [
        'Isolate affected plants and avoid overhead watering.',
        'Remove heavily infected leaves and sanitize tools.',
        'Apply a preventive fungicide or organic copper spray.',
      ],
    };
  }

  if (id.includes('yellow') || id.includes('chlorosis')) {
    return {
      label: 'Possible nutrient deficiency (nitrogen/iron)',
      confidence: clamp(confidenceBase + 7, 68, 90),
      urgency: 'medium',
      actions: [
        'Check soil pH and correct toward crop-specific range.',
        'Apply balanced nutrients or foliar micronutrient mix.',
        'Reassess in 3 to 5 days with another leaf photo.',
      ],
    };
  }

  if (format === 'png' && result.width > result.height) {
    return {
      label: 'Possible pest bite pattern',
      confidence: clamp(confidenceBase + 5, 65, 88),
      urgency: 'medium',
      actions: [
        'Inspect undersides of leaves for insects or eggs.',
        'Use neem oil or biological pest controls at dusk.',
        'Repeat scouting daily for one week.',
      ],
    };
  }

  return {
    label: 'No strong disease signal detected',
    confidence: clamp(confidenceBase, 60, 86),
    urgency: 'low',
    actions: [
      'Continue monitoring and capture another image in 48 hours.',
      'Keep airflow high and avoid prolonged leaf wetness.',
      'Track any changes in color, spots, or curling.',
    ],
  };
}

function getWateringRecommendation(
  sensors: SensorSnapshot,
  stage: CropStage,
  rainChance: number
): { decision: string; amountLiters: number; note: string } {
  const stageFactor = stage === 'seedling' ? 0.75 : stage === 'vegetative' ? 1 : 1.2;
  const dryness = clamp((55 - sensors.soilMoisture) / 20, 0, 2.2);
  const heatBoost = clamp((sensors.temperatureC - 28) / 10, 0, 1);
  const humidityRelief = clamp((70 - sensors.humidity) / 30, 0, 1);
  const rainRelief = clamp(rainChance / 100, 0, 0.8);

  const liters = clamp((1.4 + dryness + heatBoost + humidityRelief - rainRelief) * stageFactor, 0.3, 3.6);

  if (sensors.soilMoisture < 32 && rainChance < 40) {
    return {
      decision: 'Water now',
      amountLiters: Number(liters.toFixed(1)),
      note: 'Moisture is below the safe band. Use drip irrigation in one cycle.',
    };
  }

  if (sensors.soilMoisture >= 32 && sensors.soilMoisture <= 58 && rainChance >= 55) {
    return {
      decision: 'Delay watering',
      amountLiters: 0,
      note: 'Soil is acceptable and forecasted rain may cover crop demand.',
    };
  }

  return {
    decision: 'Light watering',
    amountLiters: Number((liters * 0.6).toFixed(1)),
    note: 'Run a short cycle and re-check soil moisture after 90 minutes.',
  };
}

function parseTimestampToSeconds(value: string): number {
  const [mm, ss] = value.split(':').map((v) => Number(v));
  if (Number.isNaN(mm) || Number.isNaN(ss)) {
    return 0;
  }
  return mm * 60 + ss;
}

function parseFarmSegments(text: string): ParsedFarmSegment[] {
  const rows = text.split('\n');
  const segments: ParsedFarmSegment[] = [];
  const re = /^\[(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\]\s*(.+)$/;

  for (const row of rows) {
    const match = row.trim().match(re);
    if (!match) {
      continue;
    }
    const startLabel = match[1];
    const endLabel = match[2];
    const title = match[3];
    const startSec = parseTimestampToSeconds(startLabel);
    const endSec = parseTimestampToSeconds(endLabel);
    segments.push({
      startLabel,
      endLabel,
      title,
      startSec,
      endSec: endSec > startSec ? endSec : startSec + 5,
    });
  }

  return segments;
}

function computeEt(temperature: number, light: number): number {
  const lightFactor = light / 1000;
  return Math.max(0, 0.0023 * (temperature + 17.8) * lightFactor);
}

function computeDryness(moisture: number): number {
  return clamp(1 - moisture / 100, 0, 1);
}

function computeStressFactor(airQuality: number): number {
  const stress = clamp(1 - airQuality / 100, 0, 1);
  return 1 + 0.3 * stress;
}

function rainAdjustment(rainExpected: boolean): number {
  return rainExpected ? 0.3 : 1.0;
}

function computeWaterNeed(
  temperature: number,
  light: number,
  moisture: number,
  airQuality: number,
  rainExpected: boolean
): number {
  return (
    computeEt(temperature, light) *
    computeDryness(moisture) *
    computeStressFactor(airQuality) *
    rainAdjustment(rainExpected)
  );
}

function decideIrrigation(waterNeed: number): { action: 'water' | 'skip'; amountMl: number } {
  if (waterNeed > 0.025) {
    return { action: 'water', amountMl: 400 };
  }
  if (waterNeed > 0.015) {
    return { action: 'water', amountMl: 200 };
  }
  return { action: 'skip', amountMl: 0 };
}

function generateIrrigationReason(
  waterNeed: number,
  action: 'water' | 'skip',
  amountMl: number,
  rainExpected: boolean
): string {
  if (action === 'skip') {
    return `Water need index is ${waterNeed.toFixed(4)} and below threshold, so irrigation is skipped for now.`;
  }
  if (rainExpected) {
    return `Rain is expected, so irrigation is reduced to ${amountMl} ml based on a water need index of ${waterNeed.toFixed(4)}.`;
  }
  return `No major rain expected and water need index is ${waterNeed.toFixed(4)}, so irrigate with ${amountMl} ml.`;
}

function getLinePath(values: number[], width = 300, height = 96): string {
  if (values.length === 0) return '';
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const stepX = values.length > 1 ? width / (values.length - 1) : width;

  return values
    .map((value, index) => {
      const x = index * stepX;
      const y = height - ((value - min) / range) * height;
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(' ');
}

function getAreaPath(values: number[], width = 300, height = 96): string {
  if (values.length === 0) return '';
  const line = getLinePath(values, width, height);
  return `${line} L ${width} ${height} L 0 ${height} Z`;
}

function formatTrendLabel(date: Date): string {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function generateNextTrendPoint(previous: SensorTrendPoint, tick: number, clock: Date): SensorTrendPoint {
  const hour = clock.getHours() + clock.getMinutes() / 60;
  const daylightFactor = Math.max(0, Math.sin(((hour - 6) / 12) * Math.PI));
  const randomDelta = () => Math.random() - 0.5;

  let moisture = clamp(previous.moisture - 0.45 + Math.cos(tick / 3.8) * 0.6 + randomDelta() * 1.3, 26, 72);
  if (moisture < 31) {
    moisture = clamp(moisture + 5.5, 26, 72);
  }

  const temperatureC = clamp(
    previous.temperatureC + Math.sin(tick / 4.2) * 0.6 + (daylightFactor - 0.4) * 0.5 + randomDelta() * 0.8,
    17,
    39
  );
  const airQuality = clamp(
    previous.airQuality + Math.cos(tick / 5.1) * 1.3 + randomDelta() * 2.2,
    48,
    93
  );
  const lightLux = clamp(
    daylightFactor * 23000 + Math.sin(tick / 2.4) * 700 + randomDelta() * 900,
    300,
    28000
  );

  return {
    label: formatTrendLabel(clock),
    temperatureC: Math.round(temperatureC),
    airQuality: Math.round(airQuality),
    moisture: Math.round(moisture),
    lightLux: Math.round(lightLux),
  };
}

interface TrendCardProps {
  title: string;
  subtitle: string;
  valueSuffix: string;
  rangeSuffix: string;
  metric: TrendMetricKey;
  points: SensorTrendPoint[];
  className: string;
  formatter?: (value: number) => string;
}

function TrendCard({
  title,
  subtitle,
  valueSuffix,
  rangeSuffix,
  metric,
  points,
  className,
  formatter,
}: TrendCardProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const values = useMemo(() => points.map((point) => point[metric]), [metric, points]);
  const linePath = useMemo(() => getLinePath(values), [values]);
  const areaPath = useMemo(() => getAreaPath(values), [values]);
  const currentValue = values[values.length - 1];
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const displayValue = formatter ? formatter(currentValue) : `${currentValue}`;
  const displayMin = formatter ? formatter(minValue) : `${minValue}`;
  const displayMax = formatter ? formatter(maxValue) : `${maxValue}`;
  const activeIndex = hoveredIndex ?? values.length - 1;
  const activePoint = points[activeIndex];
  const activeValue = values[activeIndex];
  const width = 300;
  const stepX = values.length > 1 ? width / (values.length - 1) : width;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const dotX = activeIndex * stepX;
  const dotY = 96 - ((activeValue - min) / range) * 96;

  const handleMouseMove = (event: React.MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = clamp((event.clientX - rect.left) / rect.width, 0, 1);
    const index = Math.round(ratio * (values.length - 1));
    setHoveredIndex(index);
  };

  return (
    <article className={`trend-card ${className}`}>
      <div className="trend-card-header">
        <h3>{title}</h3>
        <strong>
          {displayValue}
          {valueSuffix}
        </strong>
      </div>
      <p className="trend-meta">{subtitle}</p>
      <div className="trend-chart-wrap">
        <svg
          viewBox="0 0 300 96"
          className="trend-chart"
          role="img"
          aria-label={`${title} trend line chart`}
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoveredIndex(null)}
        >
          <path d={areaPath} className="trend-area" />
          <path d={linePath} />
          <line x1={dotX} x2={dotX} y1={0} y2={96} className="trend-crosshair" />
          <circle cx={dotX} cy={dotY} r={4} className="trend-dot" />
        </svg>
        <div className="trend-tooltip">
          <span>{activePoint.label}</span>
          <strong>
            {formatter ? formatter(activeValue) : activeValue}
            {valueSuffix}
          </strong>
        </div>
      </div>
      <p className="trend-range">
        Range: {displayMin}
        {rangeSuffix} - {displayMax}
        {rangeSuffix}
      </p>
    </article>
  );
}

async function geocodeCity(city: string): Promise<{ latitude: number; longitude: number }> {
  const response = await fetch(
    `https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(city)}&count=1`
  );
  if (!response.ok) {
    throw new Error('Could not geocode city.');
  }
  const data = (await response.json()) as { results?: Array<{ latitude: number; longitude: number }> };
  const first = data.results?.[0];
  if (!first) {
    throw new Error(`No geocoding result found for "${city}".`);
  }
  return { latitude: first.latitude, longitude: first.longitude };
}

async function fetchRainExpected(latitude: number, longitude: number): Promise<{
  rainExpected: boolean;
  weatherSummary: string;
}> {
  const params = new URLSearchParams({
    latitude: latitude.toString(),
    longitude: longitude.toString(),
    hourly: 'precipitation_probability',
    forecast_days: '1',
    timezone: 'auto',
  });
  const response = await fetch(`https://api.open-meteo.com/v1/forecast?${params.toString()}`);
  if (!response.ok) {
    throw new Error('Could not fetch weather forecast.');
  }
  const data = (await response.json()) as { hourly?: { precipitation_probability?: number[] } };
  const precipitation = data.hourly?.precipitation_probability ?? [];
  const maxProbability = precipitation.length > 0 ? Math.max(...precipitation) : 0;
  return {
    rainExpected: maxProbability >= 50,
    weatherSummary: `Max precip probability today: ${maxProbability}%`,
  };
}

function getPageFromPath(pathname: string): AppPage {
  if (pathname === '/twelvelabs' || pathname.startsWith('/twelvelabs/')) {
    return 'twelvelabs';
  }
  if (pathname === '/cloudinary' || pathname.startsWith('/cloudinary/')) {
    return 'cloudinary';
  }
  if (pathname === '/disease-analysis' || pathname.startsWith('/disease-analysis/')) {
    return 'diseaseAnalysis';
  }
  if (pathname === '/irrigator' || pathname.startsWith('/irrigator/')) {
    return 'irrigator';
  }
  return 'dashboard';
}

function getRouteFromPath(pathname: string): AppRoute {
  if (pathname === '/') {
    return 'landing';
  }
  return getPageFromPath(pathname);
}

function App({ authEnabled = false }: AppProps) {
  const { isAuthenticated, user, logout, loginWithRedirect } = useAuth0();
  const [activeRoute, setActiveRoute] = useState<AppRoute>(() => getRouteFromPath(window.location.pathname));
  const [activePage, setActivePage] = useState<AppPage>(() => getPageFromPath(window.location.pathname));
  const [sensors, setSensors] = useState<SensorSnapshot>(INITIAL_SENSORS);
  const [cropStage, setCropStage] = useState<CropStage>('vegetative');
  const [rainChance, setRainChance] = useState(35);
  const [latestUpload, setLatestUpload] = useState<CloudinaryUploadResult | null>(null);
  const [diagnosis, setDiagnosis] = useState<DiagnosisResult | null>(null);
  const [agentDecision, setAgentDecision] = useState<DecisionResponseApi | null>(null);
  const [agentExplanation, setAgentExplanation] = useState('');
  const [agentMode, setAgentMode] = useState<'local' | 'backend'>('backend');
  const [isDeciding, setIsDeciding] = useState(false);
  const [videoUrlInput, setVideoUrlInput] = useState('');
  const [lastIngestedSourceUrl, setLastIngestedSourceUrl] = useState('');
  const [isIngestingVideo, setIsIngestingVideo] = useState(false);
  const [lastIngestionResult, setLastIngestionResult] = useState<TwelvelabsIngestionResultApi | null>(null);
  const [twelvelabsHistory, setTwelvelabsHistory] = useState<TwelvelabsHistoryItemApi[]>([]);
  const [indexedVideos, setIndexedVideos] = useState<TwelvelabsIndexVideoApi[]>([]);
  const [selectedVideoId, setSelectedVideoId] = useState('');
  const [summaryType, setSummaryType] = useState<'summary' | 'chapter' | 'highlight'>('summary');
  const [summaryPrompt, setSummaryPrompt] = useState('');
  const [summaryOutput, setSummaryOutput] = useState('');
  const [isSummarizing, setIsSummarizing] = useState(false);
  const [videoQuestion, setVideoQuestion] = useState('');
  const [qnaOutput, setQnaOutput] = useState('');
  const [isAskingQna, setIsAskingQna] = useState(false);
  const [farmSegmentsOutput, setFarmSegmentsOutput] = useState('');
  const [isGeneratingFarmSegments, setIsGeneratingFarmSegments] = useState(false);
  const [activeSegmentEndSec, setActiveSegmentEndSec] = useState<number | null>(null);
  const [isLoadingIndexVideos, setIsLoadingIndexVideos] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [uploadMessage, setUploadMessage] = useState('');
  const [cloudinaryMessage, setCloudinaryMessage] = useState('');
  const [cloudinaryLatest, setCloudinaryLatest] = useState<CloudinaryLatestResponseApi | null>(null);
  const [cloudinaryEvents, setCloudinaryEvents] = useState<CloudinaryEventRowApi[]>([]);
  const [isLoadingCloudinary, setIsLoadingCloudinary] = useState(false);
  const [cloudinaryLastUpload, setCloudinaryLastUpload] = useState<CloudinaryUploadResult | null>(null);
  const [isRunningLocalCloudinary, setIsRunningLocalCloudinary] = useState(false);
  const [irrigatorForm, setIrrigatorForm] = useState<IrrigatorFormState>(INITIAL_IRRIGATOR_FORM);
  const [irrigatorResult, setIrrigatorResult] = useState<IrrigatorResult | null>(null);
  const [irrigatorChat, setIrrigatorChat] = useState<IrrigatorChatMessage[]>([]);
  const [irrigatorChatInput, setIrrigatorChatInput] = useState('');
  const [isRunningIrrigator, setIsRunningIrrigator] = useState(false);
  const [irrigatorError, setIrrigatorError] = useState('');
  const [trendPoints, setTrendPoints] = useState<SensorTrendPoint[]>(SENSOR_TREND_DATA);
  const [trendTick, setTrendTick] = useState(SENSOR_TREND_DATA.length);
  const [trendWindow, setTrendWindow] = useState<12 | 24>(24);
  const [isTrendLive, setIsTrendLive] = useState(true);
  const [diseasePreviewUrl, setDiseasePreviewUrl] = useState('');
  const [diseasePreviewName, setDiseasePreviewName] = useState('');
  const [isDragOverDiseaseDropzone, setIsDragOverDiseaseDropzone] = useState(false);
  const [diseaseUploadFile, setDiseaseUploadFile] = useState<File | null>(null);
  const [diseasePredictions, setDiseasePredictions] = useState<DiseasePredictionItem[]>([]);
  const [isClassifyingDisease, setIsClassifyingDisease] = useState(false);
  const [diseaseClassificationError, setDiseaseClassificationError] = useState('');
  const [typedLandingTagline, setTypedLandingTagline] = useState(LANDING_TAGLINE);
  const [typedLandingHeading, setTypedLandingHeading] = useState(LANDING_HEADING);
  const indexedPreviewVideoRef = useRef<HTMLVideoElement | null>(null);
  const diseaseFileInputRef = useRef<HTMLInputElement | null>(null);
  const [accountDropdownOpen, setAccountDropdownOpen] = useState(false);
  const classifierApiBase = (import.meta.env.VITE_CLASSIFIER_API_URL as string | undefined)?.trim() || 'http://127.0.0.1:8010';

  const cloudinaryWidgetOptions = useMemo(
    () => ({
      tags: ['agrimind-ui'],
      folder: 'agrimind/web',
    }),
    []
  );

  const runDecisionFlow = async (nextUpload?: CloudinaryUploadResult | null) => {
    if (agentMode !== 'backend') {
      return;
    }

    setIsDeciding(true);
    setUploadMessage('Running Fetch.ai decision pipeline...');

    try {
      const decision = await getAgentDecision({
        sensors: mapSensorsToApi(sensors),
        cropStage,
        rainChance,
        latestUpload: nextUpload ?? latestUpload,
        plantType: 'tomato',
      });
      setAgentDecision(decision);
      const explanation = await getDecisionExplanation(decision);
      setAgentExplanation(explanation);
      setUploadMessage('Agent decision completed.');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown backend error.';
      setUploadMessage(`Backend decision failed: ${message}`);
    } finally {
      setIsDeciding(false);
    }
  };

  const handleUploadSuccess = (result: CloudinaryUploadResult) => {
    if (result.resource_type !== 'image' && result.resource_type !== 'video') {
      setUploadMessage('Please upload a plant image or short growth video.');
      return;
    }

    setLatestUpload(result);

    if (agentMode === 'backend') {
      void runDecisionFlow(result);
      return;
    }

    if (result.resource_type === 'video') {
      setUploadMessage('Video uploaded. Switch to backend mode to run TwelveLabs ingestion.');
      return;
    }

    setDiagnosis(runLeafDiagnosis(result));
    setUploadMessage('Leaf image analyzed in local mode. Review diagnosis below.');
  };

  const loadTwelvelabsHistory = async () => {
    setIsLoadingHistory(true);
    try {
      const history = await getTwelvelabsHistory(20);
      setTwelvelabsHistory(history);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to load TwelveLabs history.';
      setUploadMessage(message);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  const loadIndexedVideos = async () => {
    setIsLoadingIndexVideos(true);
    try {
      const result = await getTwelvelabsIndexVideos({ limit: 30 });
      setIndexedVideos(result.videos || []);
      if (result.error) {
        setUploadMessage(`TwelveLabs video list warning: ${result.error}`);
      } else if (!selectedVideoId && result.videos.length > 0) {
        setSelectedVideoId(result.videos[0].video_id);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to load indexed videos.';
      setUploadMessage(message);
    } finally {
      setIsLoadingIndexVideos(false);
    }
  };

  const handleDirectVideoIngestion = async () => {
    if (!videoUrlInput.trim()) {
      setUploadMessage('Enter a public video URL to ingest into TwelveLabs.');
      return;
    }

    setIsIngestingVideo(true);
    try {
      const sourceUrl = videoUrlInput.trim();
      const result = await ingestVideoToTwelvelabs({
        videoUrl: sourceUrl,
        sourceKey: latestUpload?.public_id,
      });
      setLastIngestionResult(result);
      setLastIngestedSourceUrl(sourceUrl);
      if (result.video_id) {
        setSelectedVideoId(result.video_id);
      }
      setUploadMessage(`TwelveLabs ingest: ${result.summary}`);
      await loadTwelvelabsHistory();
      await loadIndexedVideos();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to ingest video into TwelveLabs.';
      setUploadMessage(message);
    } finally {
      setIsIngestingVideo(false);
    }
  };

  const handleSummarizeVideo = async () => {
    if (!selectedVideoId) {
      setUploadMessage('Select a video from index before generating summary.');
      return;
    }

    setIsSummarizing(true);
    try {
      const result = await summarizeIndexedVideo({
        videoId: selectedVideoId,
        summaryType,
        prompt: summaryPrompt,
      });
      if (result.status === 'ready') {
        setSummaryOutput(result.text || 'No summary text returned.');
      } else {
        setSummaryOutput('');
        setUploadMessage(`Summary failed: ${result.error || 'Unknown error'}`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to summarize video.';
      setUploadMessage(message);
    } finally {
      setIsSummarizing(false);
    }
  };

  const handleAskQna = async () => {
    if (!selectedVideoId) {
      setUploadMessage('Select a video from index before asking Q&A.');
      return;
    }

    if (!videoQuestion.trim()) {
      setUploadMessage('Enter a question for the selected video.');
      return;
    }

    setIsAskingQna(true);
    try {
      const result = await askIndexedVideoQuestion({
        videoId: selectedVideoId,
        question: videoQuestion.trim(),
      });
      if (result.status === 'ready') {
        setQnaOutput(result.text || 'No answer text returned.');
      } else {
        setQnaOutput('');
        setUploadMessage(`Q&A failed: ${result.error || 'Unknown error'}`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to run video Q&A.';
      setUploadMessage(message);
    } finally {
      setIsAskingQna(false);
    }
  };

  const handleGenerateFarmSegments = async () => {
    if (!selectedVideoId) {
      setUploadMessage('Select a video from index before generating farm risk segments.');
      return;
    }

    setIsGeneratingFarmSegments(true);
    setFarmSegmentsOutput('');
    try {
      const result = await askIndexedVideoQuestion({
        videoId: selectedVideoId,
        question:
          'Break down this video into important time segments for agriculture operations. Focus on machine failure, crop damage, pest pressure, irrigation system issues, nutrient stress signs, labor safety hazards, and water wastage. Return in this format:\n[MM:SS - MM:SS] Segment title\n- Why it matters\n- Recommended action',
      });
      if (result.status === 'ready') {
        setFarmSegmentsOutput(result.text || 'No segment breakdown returned.');
      } else {
        setUploadMessage(`Farm segment breakdown failed: ${result.error || 'Unknown error'}`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to generate farm segment breakdown.';
      setUploadMessage(message);
    } finally {
      setIsGeneratingFarmSegments(false);
    }
  };

  const loadCloudinaryData = useCallback(async () => {
    setIsLoadingCloudinary(true);
    try {
      const [latest, events] = await Promise.all([getCloudinaryLatest(), getCloudinaryEvents(15)]);
      setCloudinaryLatest(latest);
      setCloudinaryEvents(events);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Could not load Cloudinary pipeline data.';
      setCloudinaryMessage(`Error: ${message}`);
    } finally {
      setIsLoadingCloudinary(false);
    }
  }, []);

  const handleCloudinaryPageUpload = (result: CloudinaryUploadResult) => {
    setCloudinaryLastUpload(result);
    setCloudinaryMessage(
      `Uploaded ${result.resource_type} "${result.public_id}". Configure your upload preset to notify \`POST /api/cloudinary/webhook\`, then wait a few seconds — or use Refresh / auto-refresh.`
    );
    let n = 0;
    const id = window.setInterval(() => {
      n += 1;
      void loadCloudinaryData();
      if (n >= 6) {
        window.clearInterval(id);
      }
    }, 2500);
  };

  const handleRunLocalCloudinaryAnalysis = async () => {
    if (!cloudinaryLastUpload) {
      setCloudinaryMessage('Upload an image/video first, then run local analysis.');
      return;
    }
    setIsRunningLocalCloudinary(true);
    try {
      const res = await runCloudinaryLocalAnalyze(cloudinaryLastUpload);
      setCloudinaryMessage(
        `Local analysis complete (${res.status}). Stored event for ${res.public_id}.`
      );
      await loadCloudinaryData();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Local cloudinary analysis failed.';
      setCloudinaryMessage(`Error: ${message}`);
    } finally {
      setIsRunningLocalCloudinary(false);
    }
  };

  useEffect(() => {
    void loadTwelvelabsHistory();
    void loadIndexedVideos();
  }, []);

  useEffect(() => {
    if (activePage === 'cloudinary') {
      void loadCloudinaryData();
    }
  }, [activePage, loadCloudinaryData]);

  useEffect(() => {
    const onPopState = () => {
      const pathname = window.location.pathname;
      setActiveRoute(getRouteFromPath(pathname));
      setActivePage(getPageFromPath(pathname));
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  useEffect(() => {
    const scriptId = 'elevenlabs-convai-script';
    if (document.getElementById(scriptId)) {
      return;
    }
    const script = document.createElement('script');
    script.id = scriptId;
    script.src = 'https://unpkg.com/@elevenlabs/convai-widget-embed';
    script.async = true;
    script.type = 'text/javascript';
    document.body.appendChild(script);
  }, []);

  useEffect(() => {
    if (activePage !== 'dashboard' || !isTrendLive) {
      return;
    }
    const timer = window.setInterval(() => {
      setTrendPoints((previous) => {
        const last = previous[previous.length - 1];
        const now = new Date();
        const nextPoint = generateNextTrendPoint(last, trendTick + 1, now);
        const updated = [...previous, nextPoint];
        return updated.slice(-TREND_POINT_LIMIT);
      });
      setTrendTick((prev) => prev + 1);
    }, TREND_REFRESH_MS);

    return () => window.clearInterval(timer);
  }, [activePage, isTrendLive, trendTick]);

  useEffect(() => {
    return () => {
      if (diseasePreviewUrl) {
        URL.revokeObjectURL(diseasePreviewUrl);
      }
    };
  }, [diseasePreviewUrl]);

  useEffect(() => {
    if (activeRoute !== 'landing') {
      setTypedLandingTagline(LANDING_TAGLINE);
      setTypedLandingHeading(LANDING_HEADING);
      return;
    }

    let cancelled = false;
    const timeoutIds: number[] = [];

    const wait = (ms: number): Promise<void> =>
      new Promise((resolve) => {
        const id = window.setTimeout(resolve, ms);
        timeoutIds.push(id);
      });

    const runTypingLoop = async () => {
      while (!cancelled) {
        setTypedLandingTagline('');
        setTypedLandingHeading('');

        for (let i = 1; i <= LANDING_TAGLINE.length; i += 1) {
          if (cancelled) return;
          setTypedLandingTagline(LANDING_TAGLINE.slice(0, i));
          await wait(42);
        }

        await wait(180);

        for (let i = 1; i <= LANDING_HEADING.length; i += 1) {
          if (cancelled) return;
          setTypedLandingHeading(LANDING_HEADING.slice(0, i));
          await wait(35);
        }

        await wait(15000);
      }
    };

    void runTypingLoop();

    return () => {
      cancelled = true;
      timeoutIds.forEach((id) => window.clearTimeout(id));
    };
  }, [activeRoute]);

  const navigateToPage = (page: AppPage) => {
    if (authEnabled && !isAuthenticated) {
      navigateToAuth();
      return;
    }
    const targetPath =
      page === 'twelvelabs'
        ? '/twelvelabs'
        : page === 'cloudinary'
          ? '/cloudinary'
          : page === 'diseaseAnalysis'
            ? '/disease-analysis'
          : page === 'irrigator'
            ? '/irrigator'
            : '/';
    if (window.location.pathname !== targetPath) {
      window.history.pushState({}, '', targetPath);
    }
    setActiveRoute(page);
    setActivePage(page);
  };

  const navigateToLanding = () => {
    if (window.location.pathname !== '/') {
      window.history.pushState({}, '', '/');
    }
    setActiveRoute('landing');
  };

  const navigateToAuth = () => {
    if (authEnabled) {
      void loginWithRedirect();
    } else {
      navigateToLanding();
    }
  };

  const handleUploadError = (error: Error) => {
    setUploadMessage(`Upload failed: ${error.message}`);
  };

  const applyDiseasePreviewFile = (file: File) => {
    if (!file.type.startsWith('image/')) {
      return;
    }
    if (diseasePreviewUrl) {
      URL.revokeObjectURL(diseasePreviewUrl);
    }
    const objectUrl = URL.createObjectURL(file);
    setDiseasePreviewUrl(objectUrl);
    setDiseasePreviewName(file.name);
    setDiseaseUploadFile(file);
    setDiseasePredictions([]);
    setDiseaseClassificationError('');
  };

  const handleDiseaseFileInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    applyDiseasePreviewFile(file);
    event.target.value = '';
  };

  const handleDiseaseDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragOverDiseaseDropzone(false);
    const file = event.dataTransfer.files?.[0];
    if (!file) {
      return;
    }
    applyDiseasePreviewFile(file);
  };

  const handleRunDiseaseClassification = async () => {
    if (!diseaseUploadFile) {
      setDiseaseClassificationError('Upload an image first.');
      return;
    }

    setIsClassifyingDisease(true);
    setDiseaseClassificationError('');
    setDiseasePredictions([]);

    try {
      const formData = new FormData();
      formData.append('file', diseaseUploadFile);
      formData.append('top_k', '3');

      const response = await fetch(`${classifierApiBase}/predict`, {
        method: 'POST',
        body: formData,
      });
      const data = (await response.json()) as { predictions?: DiseasePredictionItem[]; error?: string };
      if (!response.ok) {
        throw new Error(data.error || 'Classification API request failed.');
      }
      setDiseasePredictions(data.predictions || []);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to classify image.';
      setDiseaseClassificationError(
        `${message} Start local service: python classification-model/leaf_disease_classifier.py --serve`
      );
    } finally {
      setIsClassifyingDisease(false);
    }
  };

  const healthScore = useMemo(() => scoreHealth(sensors), [sensors]);
  const healthStatus = useMemo(() => getHealthStatus(sensors), [sensors]);
  const watering = useMemo(
    () => getWateringRecommendation(sensors, cropStage, rainChance),
    [sensors, cropStage, rainChance]
  );

  const displayedDiagnosis =
    agentMode === 'backend' && agentDecision
      ? {
          label: agentDecision.disease.replace(/_/g, ' '),
          confidence: Math.round(agentDecision.diagnosis.confidence * 100),
          urgency: agentDecision.diagnosis.urgency,
          actions: agentDecision.diagnosis.actions,
        }
      : diagnosis;

  const displayedWatering =
    agentMode === 'backend' && agentDecision
      ? {
          decision: agentDecision.irrigation.action.replace(/_/g, ' '),
          amountLiters: agentDecision.irrigation.liters,
          note: agentDecision.irrigation.rationale,
        }
      : watering;

  const selectedIndexedVideo = useMemo(
    () => indexedVideos.find((video) => video.video_id === selectedVideoId) || null,
    [indexedVideos, selectedVideoId]
  );
  const previewVideoUrl =
    selectedIndexedVideo?.stream_url ||
    (lastIngestionResult?.video_id === selectedVideoId
      ? lastIngestionResult?.stream_url || lastIngestedSourceUrl
      : null);
  const parsedFarmSegments = useMemo(() => parseFarmSegments(farmSegmentsOutput), [farmSegmentsOutput]);
  const visibleTrendPoints = useMemo(() => trendPoints.slice(-trendWindow), [trendPoints, trendWindow]);

  const handlePlayFarmSegment = (segment: ParsedFarmSegment) => {
    const video = indexedPreviewVideoRef.current;
    if (!video || !previewVideoUrl) {
      setUploadMessage('Preview video is not available. Select a video with preview URL first.');
      return;
    }

    video.currentTime = segment.startSec;
    void video.play();
    setActiveSegmentEndSec(segment.endSec);
  };

  const handlePreviewTimeUpdate = () => {
    const video = indexedPreviewVideoRef.current;
    if (!video || activeSegmentEndSec === null) {
      return;
    }
    if (video.currentTime >= activeSegmentEndSec) {
      video.pause();
      setActiveSegmentEndSec(null);
    }
  };

  const runIrrigator = async () => {
    setIsRunningIrrigator(true);
    setIrrigatorError('');
    setIrrigatorResult(null);

    try {
      let latitude = Number(irrigatorForm.latitude);
      let longitude = Number(irrigatorForm.longitude);

      if (Number.isNaN(latitude) || Number.isNaN(longitude)) {
        if (!irrigatorForm.city.trim()) {
          throw new Error('Provide either city or both latitude and longitude.');
        }
        const geocoded = await geocodeCity(irrigatorForm.city.trim());
        latitude = geocoded.latitude;
        longitude = geocoded.longitude;
      }

      const weather = await fetchRainExpected(latitude, longitude);
      const waterNeed = computeWaterNeed(
        irrigatorForm.temperature,
        irrigatorForm.light,
        irrigatorForm.moisture,
        irrigatorForm.airQuality,
        weather.rainExpected
      );
      const decision = decideIrrigation(waterNeed);
      const reason = generateIrrigationReason(
        waterNeed,
        decision.action,
        decision.amountMl,
        weather.rainExpected
      );

      const result: IrrigatorResult = {
        rainExpected: weather.rainExpected,
        weatherSummary: weather.weatherSummary,
        waterNeed,
        action: decision.action,
        amountMl: decision.amountMl,
        reason,
      };
      setIrrigatorResult(result);
      setIrrigatorChat([
        {
          role: 'agent',
          text: `${weather.weatherSummary}. Decision: ${result.action.toUpperCase()} ${result.amountMl} ml. ${result.reason}`,
        },
      ]);
    } catch (error) {
      setIrrigatorError(error instanceof Error ? error.message : 'Irrigator run failed.');
    } finally {
      setIsRunningIrrigator(false);
    }
  };

  const handleIrrigatorChatSend = () => {
    const question = irrigatorChatInput.trim();
    if (!question) {
      return;
    }

    setIrrigatorChat((prev) => [...prev, { role: 'user', text: question }]);
    setIrrigatorChatInput('');

    let answer = 'Run the irrigator first so I can answer with current conditions.';
    if (irrigatorResult) {
      const q = question.toLowerCase();
      if (q.includes('why')) {
        answer = irrigatorResult.reason;
      } else if (q.includes('rain')) {
        answer = `${irrigatorResult.weatherSummary}. Rain expected: ${irrigatorResult.rainExpected ? 'yes' : 'no'}.`;
      } else if (q.includes('water need') || q.includes('index')) {
        answer = `Water need index is ${irrigatorResult.waterNeed.toFixed(4)}.`;
      } else if (q.includes('how much') || q.includes('amount')) {
        answer = `Recommended irrigation amount is ${irrigatorResult.amountMl} ml.`;
      } else {
        answer = `Action is ${irrigatorResult.action} with ${irrigatorResult.amountMl} ml. ${irrigatorResult.reason}`;
      }
    }

    setIrrigatorChat((prev) => [...prev, { role: 'agent', text: answer }]);
  };

  if (activeRoute === 'landing') {
    return (
      <div className="landing-page">
        <header className="landing-nav" aria-label="Landing navigation">
          <div className="landing-brand">AgriMind</div>
          <nav className="landing-links">
            <button type="button" onClick={() => navigateToPage('dashboard')} className="landing-link">
              Dashboard
            </button>
            <button type="button" onClick={() => navigateToPage('twelvelabs')} className="landing-link">
              TwelveLabs
            </button>
            <button type="button" onClick={() => navigateToPage('cloudinary')} className="landing-link">
              Cloudinary
            </button>
            <button type="button" onClick={() => navigateToPage('diseaseAnalysis')} className="landing-link">
              Disease Analysis
            </button>
            <button type="button" onClick={() => navigateToPage('irrigator')} className="landing-link">
              Irrigator
            </button>
          </nav>
          {authEnabled && isAuthenticated ? (
            <div className="account-dropdown">
              <button
                type="button"
                className="landing-account"
                onClick={() => setAccountDropdownOpen(!accountDropdownOpen)}
              >
                {user?.name || user?.email || 'Account'}
              </button>
              {accountDropdownOpen && (
                <div className="dropdown-menu">
                  <button
                    type="button"
                    className="dropdown-item"
                    onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
                  >
                    Log out
                  </button>
                </div>
              )}
            </div>
          ) : (
            <button type="button" className="landing-signup" onClick={() => void loginWithRedirect()}>
              Sign up
            </button>
          )}
        </header>

        <section className="landing-hero">
          <div className="landing-overlay" />
          <img
            className="landing-hero-mascot"
            src="/landing-bot-v3.png"
            alt="AgriMind helper robot"
            loading="lazy"
          />
          <div className="landing-content">
            <p className="landing-tag">{typedLandingTagline}</p>
            <h1>{typedLandingHeading}</h1>
            <p>
              Monitor crop health, analyze visual signals, and optimize irrigation from one intelligent platform.
            </p>
            <button type="button" className="landing-cta" onClick={() => navigateToPage('dashboard')}>
              Open Dashboard
            </button>
          </div>
        </section>

        <section className="landing-stats">
          <div className="stats-container">
            <div className="stat-item">
              <h3>Energy Saved</h3>
              <p className="stat-number">25%</p>
              <p>Reduced water usage through intelligent irrigation</p>
            </div>
            <div className="stat-item">
              <h3>Crop Yield</h3>
              <p className="stat-number">+15%</p>
              <p>Improved health monitoring and decision making</p>
            </div>
            <div className="stat-item">
              <h3>Time Efficiency</h3>
              <p className="stat-number">50%</p>
              <p>Automated analysis and recommendations</p>
            </div>
          </div>
        </section>
      </div>
    );
  }

  if (authEnabled && !isAuthenticated) {
    void loginWithRedirect();
    return <div>Redirecting to login...</div>;
  }

  return (
    <div className="app">
      <main className="layout">
        <header className="hero">
          <h1>
            <button type="button" className="hero-home-link" onClick={navigateToLanding}>
              AgriMind
            </button>
          </h1>
          <p>Smart micro-farming assistant for soil health, leaf diagnosis, and watering plans.</p>
        </header>

        <nav className="app-nav" aria-label="Main navigation">
          <button
            type="button"
            className={activePage === 'dashboard' ? 'nav-link active' : 'nav-link'}
            onClick={() => navigateToPage('dashboard')}
          >
            Dashboard
          </button>
          <button
            type="button"
            className={activePage === 'twelvelabs' ? 'nav-link active' : 'nav-link'}
            onClick={() => navigateToPage('twelvelabs')}
          >
            TwelveLabs
          </button>
          <button
            type="button"
            className={activePage === 'cloudinary' ? 'nav-link active' : 'nav-link'}
            onClick={() => navigateToPage('cloudinary')}
          >
            Cloudinary
          </button>
          <button
            type="button"
            className={activePage === 'diseaseAnalysis' ? 'nav-link active' : 'nav-link'}
            onClick={() => navigateToPage('diseaseAnalysis')}
          >
            Disease Analysis
          </button>
          <button
            type="button"
            className={activePage === 'irrigator' ? 'nav-link active' : 'nav-link'}
            onClick={() => navigateToPage('irrigator')}
          >
            Irrigator
          </button>
          <button type="button" className="nav-link nav-signup" onClick={navigateToAuth}>
            Sign up
          </button>
        </nav>

        {activePage === 'dashboard' && (
          <div className="dashboard-page">
        <section className="card">
          <div className="card-title-row">
            <h2>Live Farm Snapshot</h2>
            <span className="pill">Health Score: {healthScore}/100</span>
          </div>

          <div className="mode-toggle-row">
            <button
              type="button"
              className={agentMode === 'backend' ? 'mode-button active' : 'mode-button'}
              onClick={() => setAgentMode('backend')}
            >
              Fetch.ai Agent Mode
            </button>
            <button
              type="button"
              className={agentMode === 'local' ? 'mode-button active' : 'mode-button'}
              onClick={() => setAgentMode('local')}
            >
              Local Fallback Mode
            </button>
          </div>

          <p className="status">{healthStatus}</p>

          <div className="trend-toolbar">
            <div className="trend-window-group">
              <button
                type="button"
                className={trendWindow === 12 ? 'trend-toggle active' : 'trend-toggle'}
                onClick={() => setTrendWindow(12)}
              >
                Last 12
              </button>
              <button
                type="button"
                className={trendWindow === 24 ? 'trend-toggle active' : 'trend-toggle'}
                onClick={() => setTrendWindow(24)}
              >
                Last 24
              </button>
            </div>
            <button
              type="button"
              className={isTrendLive ? 'trend-live-btn active' : 'trend-live-btn'}
              onClick={() => setIsTrendLive((prev) => !prev)}
            >
              {isTrendLive ? 'Live updates ON' : 'Paused'}
            </button>
          </div>

          <div className="sensor-trend-grid">
            <TrendCard
              title="Temperature"
              subtitle="Reactive climate trend"
              metric="temperatureC"
              points={visibleTrendPoints}
              className="temperature"
              valueSuffix="C"
              rangeSuffix="C"
            />
            <TrendCard
              title="Air Quality Index"
              subtitle="Lower values are cleaner"
              metric="airQuality"
              points={visibleTrendPoints}
              className="air-quality"
              valueSuffix=" AQI"
              rangeSuffix=" AQI"
            />
            <TrendCard
              title="Humidity / Moisture"
              subtitle="Soil plus canopy moisture blend"
              metric="moisture"
              points={visibleTrendPoints}
              className="moisture"
              valueSuffix="%"
              rangeSuffix="%"
            />
            <TrendCard
              title="Light Levels"
              subtitle="Diurnal daylight simulation"
              metric="lightLux"
              points={visibleTrendPoints}
              className="light"
              valueSuffix=" lux"
              rangeSuffix=" lux"
              formatter={(value) => value.toLocaleString()}
            />
          </div>

          <div className="grid sensors-grid">
            <label>
              Soil moisture (%)
              <input
                type="range"
                min={10}
                max={90}
                value={sensors.soilMoisture}
                onChange={(event) =>
                  setSensors((prev) => ({ ...prev, soilMoisture: Number(event.target.value) }))
                }
              />
              <strong>{sensors.soilMoisture}%</strong>
            </label>

            <label>
              Temperature (C)
              <input
                type="range"
                min={10}
                max={45}
                value={sensors.temperatureC}
                onChange={(event) =>
                  setSensors((prev) => ({ ...prev, temperatureC: Number(event.target.value) }))
                }
              />
              <strong>{sensors.temperatureC}C</strong>
            </label>

            <label>
              Humidity (%)
              <input
                type="range"
                min={20}
                max={95}
                value={sensors.humidity}
                onChange={(event) =>
                  setSensors((prev) => ({ ...prev, humidity: Number(event.target.value) }))
                }
              />
              <strong>{sensors.humidity}%</strong>
            </label>

            <label>
              Light (lux)
              <input
                type="range"
                min={1000}
                max={30000}
                step={500}
                value={sensors.lightLux}
                onChange={(event) =>
                  setSensors((prev) => ({ ...prev, lightLux: Number(event.target.value) }))
                }
              />
              <strong>{sensors.lightLux.toLocaleString()} lux</strong>
            </label>

            <label>
              Soil pH
              <input
                type="range"
                min={4.5}
                max={8.5}
                step={0.1}
                value={sensors.ph}
                onChange={(event) =>
                  setSensors((prev) => ({ ...prev, ph: Number(event.target.value) }))
                }
              />
              <strong>{sensors.ph.toFixed(1)}</strong>
            </label>
          </div>
        </section>

        <section className="card">
          <div className="card-title-row">
            <h2>Disease Detection (Camera Upload)</h2>
            <span className="pill subtle">Cloudinary-backed upload</span>
          </div>

          {!hasUploadPreset && (
            <p className="warning">
              Upload preset not configured. Add `VITE_CLOUDINARY_UPLOAD_PRESET` to enable diagnosis uploads.
            </p>
          )}

          {hasUploadPreset && (
            <UploadWidget
              onUploadSuccess={handleUploadSuccess}
              onUploadError={handleUploadError}
              buttonText="Upload Leaf Photo"
            />
          )}

          {uploadMessage && <p className="status">{uploadMessage}</p>}

          {latestUpload && (
            <div className="upload-preview">
              {latestUpload.resource_type === 'video' ? (
                <video src={latestUpload.secure_url} controls />
              ) : (
                <img src={latestUpload.secure_url} alt="Uploaded leaf sample" />
              )}
              <div>
                <p>
                  <strong>Public ID:</strong> {latestUpload.public_id}
                </p>
                <p>
                  <strong>Image size:</strong> {latestUpload.width} x {latestUpload.height}
                </p>
                <p>
                  <strong>Type:</strong> {latestUpload.resource_type}
                </p>
              </div>
            </div>
          )}

          {displayedDiagnosis && (
            <div className={`diagnosis ${displayedDiagnosis.urgency}`}>
              <p>
                <strong>Result:</strong> {displayedDiagnosis.label}
              </p>
              <p>
                <strong>Confidence:</strong> {displayedDiagnosis.confidence}%
              </p>
              <p>
                <strong>Urgency:</strong> {displayedDiagnosis.urgency}
              </p>
              <ul>
                {displayedDiagnosis.actions.map((action) => (
                  <li key={action}>{action}</li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <section className="card">
          <h2>Watering Optimization</h2>
          <div className="grid controls-grid">
            <label>
              Crop stage
              <select value={cropStage} onChange={(event) => setCropStage(event.target.value as CropStage)}>
                <option value="seedling">Seedling</option>
                <option value="vegetative">Vegetative</option>
                <option value="flowering">Flowering</option>
              </select>
            </label>
            <label>
              Rain chance (%)
              <input
                type="range"
                min={0}
                max={100}
                value={rainChance}
                onChange={(event) => setRainChance(Number(event.target.value))}
              />
              <strong>{rainChance}%</strong>
            </label>
          </div>

          <div className="watering-result">
            <p>
              <strong>Decision:</strong> {displayedWatering.decision}
            </p>
            <p>
              <strong>Recommended water:</strong> {displayedWatering.amountLiters} L per bed/zone
            </p>
            <p>{displayedWatering.note}</p>
          </div>
        </section>

        <section className="card">
          <div className="card-title-row">
            <h2>Agent Decision Engine</h2>
            <span className="pill subtle">ASI-1 + Agentverse aligned flow</span>
          </div>

          <p className="status">
            {agentMode === 'backend'
              ? 'Backend mode sends sensor and image signals to the decision API.'
              : 'Local fallback mode keeps the demo running without backend dependencies.'}
          </p>

          <button type="button" className="run-decision-btn" onClick={() => void runDecisionFlow()} disabled={isDeciding}>
            {isDeciding ? 'Running decision...' : 'Run Agent Decision'}
          </button>

          {agentDecision && (
            <div className="agent-output">
              <p>
                <strong>Action:</strong> {agentDecision.action.replace(/_/g, ' ')}
              </p>
              <p>
                <strong>Recommendation:</strong> {agentDecision.recommendation}
              </p>
              <p>
                <strong>Impact:</strong> {agentDecision.impact.water_saved_ml} ml saved, risk {agentDecision.impact.risk_level}
              </p>
              {agentExplanation && <p>{agentExplanation}</p>}

              <div className="health-agent-panel">
                <p>
                  <strong>Health Severity:</strong> {agentDecision.health.severity}
                </p>
                <p>
                  <strong>Health Explanation:</strong> {agentDecision.health.explanation}
                </p>
                {agentDecision.health.visual_history_url && (
                  <p>
                    <strong>Visual History:</strong>{' '}
                    <a href={agentDecision.health.visual_history_url} target="_blank" rel="noreferrer">
                      Open Cloudinary asset
                    </a>
                  </p>
                )}
                <p>
                  <strong>TwelveLabs Status:</strong> {agentDecision.health.twelvelabs_status || 'n/a'}
                </p>
                {agentDecision.health.twelvelabs_indexed_asset_id && (
                  <p>
                    <strong>Indexed Asset:</strong> {agentDecision.health.twelvelabs_indexed_asset_id}
                  </p>
                )}
                {agentDecision.health.twelvelabs_stream_url && (
                  <p>
                    <strong>Stream URL:</strong>{' '}
                    <a href={agentDecision.health.twelvelabs_stream_url} target="_blank" rel="noreferrer">
                      Open stream
                    </a>
                  </p>
                )}
                {agentDecision.health.twelvelabs_search_reference && (
                  <p>
                    <strong>Search Ref:</strong> {agentDecision.health.twelvelabs_search_reference}
                  </p>
                )}
              </div>
            </div>
          )}
        </section>

        <div className="dashboard-convai-widget" aria-label="AgriMind voice assistant widget">
          {createElement('elevenlabs-convai', {
            'agent-id': 'agent_9501kmv3szh3emn8r5b915eewaq0',
          })}
        </div>
          </div>
        )}

        {activePage === 'twelvelabs' && (
          <section className="card">
            <div className="card-title-row">
              <h2>Direct Video Ingestion (TwelveLabs)</h2>
              <span className="pill subtle">Standalone video intelligence page</span>
            </div>

            <p className="status">
              Use a public raw video URL if you want to ingest independently from Cloudinary uploads.
              Cloudinary video links are supported here.
            </p>

            {uploadMessage && <p className="status">{uploadMessage}</p>}

            <div className="video-ingest-panel">
              <input
                type="url"
                value={videoUrlInput}
                onChange={(event) => setVideoUrlInput(event.target.value)}
                placeholder="https://.../plant-growth.mp4"
              />
              <button type="button" onClick={() => void handleDirectVideoIngestion()} disabled={isIngestingVideo}>
                {isIngestingVideo ? 'Ingesting...' : 'Ingest Video URL'}
              </button>
              {lastIngestionResult && (
                <p>
                  <strong>Last Ingestion:</strong> {lastIngestionResult.status} - {lastIngestionResult.summary}
                </p>
              )}
            </div>

            <div className="video-insight-panel">
              <div className="card-title-row">
                <h3>TwelveLabs Video Intelligence</h3>
                <button type="button" onClick={() => void loadIndexedVideos()} disabled={isLoadingIndexVideos}>
                  {isLoadingIndexVideos ? 'Loading...' : 'Refresh Index Videos'}
                </button>
              </div>

              <label>
                Select video from existing index
                <select value={selectedVideoId} onChange={(event) => setSelectedVideoId(event.target.value)}>
                  <option value="">Choose an indexed video</option>
                  {indexedVideos.map((video) => (
                    <option key={video.video_id} value={video.video_id}>
                      {video.filename || video.video_id}
                    </option>
                  ))}
                </select>
              </label>

              <div className="video-preview-panel">
                <h4>Indexed Video Preview</h4>
                {!selectedVideoId ? (
                  <p>Select an indexed video to preview it here.</p>
                ) : previewVideoUrl ? (
                  <video ref={indexedPreviewVideoRef} src={previewVideoUrl} controls onTimeUpdate={handlePreviewTimeUpdate} />
                ) : (
                  <p>
                    No stream preview URL available for this video yet. Re-ingest with streaming enabled or pick another
                    indexed video.
                  </p>
                )}
              </div>

              <div className="summary-controls">
                <label>
                  Summary type
                  <select value={summaryType} onChange={(event) => setSummaryType(event.target.value as 'summary' | 'chapter' | 'highlight')}>
                    <option value="summary">Summary</option>
                    <option value="chapter">Chapter</option>
                    <option value="highlight">Highlight</option>
                  </select>
                </label>

                <label>
                  Optional custom summary prompt
                  <input
                    type="text"
                    value={summaryPrompt}
                    onChange={(event) => setSummaryPrompt(event.target.value)}
                    placeholder="Focus on disease progression and actionable insights"
                  />
                </label>

                <button type="button" onClick={() => void handleSummarizeVideo()} disabled={isSummarizing}>
                  {isSummarizing ? 'Generating summary...' : 'Generate AI Summary'}
                </button>

                {summaryOutput && <p className="text-output">{summaryOutput}</p>}
              </div>

              <div className="summary-controls">
                <button
                  type="button"
                  onClick={() => void handleGenerateFarmSegments()}
                  disabled={isGeneratingFarmSegments}
                >
                  {isGeneratingFarmSegments ? 'Breaking into farm segments...' : 'Generate Farm Risk Segments'}
                </button>
                {farmSegmentsOutput && <p className="text-output">{farmSegmentsOutput}</p>}
                {parsedFarmSegments.length > 0 && (
                  <div className="segment-preview-list">
                    <h4>Segment Previews</h4>
                    {parsedFarmSegments.map((segment) => (
                      <div key={`${segment.startLabel}-${segment.endLabel}-${segment.title}`} className="segment-preview-row">
                        <div>
                          <strong>
                            [{segment.startLabel} - {segment.endLabel}]
                          </strong>{' '}
                          {segment.title}
                        </div>
                        <button
                          type="button"
                          onClick={() => handlePlayFarmSegment(segment)}
                          disabled={!previewVideoUrl}
                        >
                          Play Segment
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="qna-controls">
                <label>
                  Ask Q&A about selected video
                  <input
                    type="text"
                    value={videoQuestion}
                    onChange={(event) => setVideoQuestion(event.target.value)}
                    placeholder="What signs of disease progression are visible?"
                  />
                </label>

                <button type="button" onClick={() => void handleAskQna()} disabled={isAskingQna}>
                  {isAskingQna ? 'Getting answer...' : 'Ask Video Q&A'}
                </button>

                {qnaOutput && <p className="text-output">{qnaOutput}</p>}
              </div>
            </div>

            <div className="twelvelabs-log-panel">
              <div className="card-title-row">
                <h3>TwelveLabs Ingestion Logs</h3>
                <button type="button" onClick={() => void loadTwelvelabsHistory()} disabled={isLoadingHistory}>
                  {isLoadingHistory ? 'Refreshing...' : 'Refresh Logs'}
                </button>
              </div>
              {twelvelabsHistory.length === 0 ? (
                <p>No ingestion logs yet.</p>
              ) : (
                <ul>
                  {twelvelabsHistory.slice(0, 8).map((entry) => (
                    <li key={`${entry.created_at}-${entry.indexed_asset_id || entry.asset_id || entry.status}`}>
                      {entry.created_at} | {entry.status} | index: {entry.index_id || 'n/a'} | indexed asset:{' '}
                      {entry.indexed_asset_id || 'n/a'}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>
        )}

        {activePage === 'cloudinary' && (
          <section className="card cloudinary-page">
            <div className="card-title-row">
              <h2>Cloudinary media pipeline</h2>
              <span className="pill subtle">Webhooks + transform URLs + backend AI</span>
            </div>

            <div className="info-callout">
              <p>
                <strong>What this tab is for:</strong> upload media to Cloudinary here (same account as the rest of the
                app). If your Cloudinary <em>upload preset</em> or project sends HTTP notifications to your AgriMind
                API <code>POST /api/cloudinary/webhook</code>, the server runs the same analysis as the event-driven
                pipeline and stores <strong>transformation URLs</strong> (thumbnail, preview, text overlay with risk /
                moisture hints). This is how you get <strong>“annotated” images</strong> for demos: they are
                Cloudinary delivery URLs with baked-in text layers — not a file attached inside the ASI:One chat.
              </p>
              <p>
                <strong>ASI:One:</strong> the orchestrator tool <code>agri.cloudinary_latest</code> returns{' '}
                <strong>JSON</strong> that includes those URLs and sustainability text. Chat clients may show the links;
                for actual images, open the URLs or use this page.
              </p>
              <p>
                <strong>Two different “base URLs”:</strong>{' '}
                <code>VITE_API_BASE_URL</code> (in the <em>browser</em> .env) points this React app at your FastAPI
                server for <code>/api/...</code>. <code>AGRIMIND_API_BASE</code> (in the <em>orchestrator agent’s</em>{' '}
                <code>backend/.env</code>) is only for the uAgent process: it is the same API base the agent uses to
                call <code>GET /api/cloudinary/latest</code>. If the agent runs on your PC and the API is on localhost,
                the default <code>http://127.0.0.1:8000</code> is enough. If the agent runs in the cloud, set it to
                your public API URL.
              </p>
            </div>

            {!hasUploadPreset && (
              <p className="warning">
                Add <code>VITE_CLOUDINARY_UPLOAD_PRESET</code> so uploads work from this tab.
              </p>
            )}

            {hasUploadPreset && (
              <div className="cloudinary-upload-block">
                <h3>Upload (image or short video)</h3>
                <p className="status">
                  Optional tags/folder: <code>agrimind-ui</code> / <code>agrimind/web</code>. In the Cloudinary
                  console, set the preset’s <strong>Notification URL</strong> to your public backend{' '}
                  <code>https://&lt;host&gt;/api/cloudinary/webhook</code> for automatic analysis.
                </p>
                <UploadWidget
                  buttonText="Upload to Cloudinary"
                  onUploadSuccess={handleCloudinaryPageUpload}
                  onUploadError={(err) => setCloudinaryMessage(`Upload error: ${err.message}`)}
                  className="cloudinary-upload-btn"
                  widgetOptions={cloudinaryWidgetOptions}
                />
                <button
                  type="button"
                  className="nav-link"
                  onClick={() => void handleRunLocalCloudinaryAnalysis()}
                  disabled={isRunningLocalCloudinary || !cloudinaryLastUpload}
                  style={{ marginLeft: '0.6rem', cursor: isRunningLocalCloudinary ? 'wait' : 'pointer' }}
                >
                  {isRunningLocalCloudinary ? 'Running local analysis…' : 'Run local analysis now (no webhook)'}
                </button>
              </div>
            )}

            {cloudinaryMessage && <p className="status cloudinary-inline-msg">{cloudinaryMessage}</p>}

            <div className="card-title-row cloudinary-toolbar">
              <h3>Latest webhook result</h3>
              <button
                type="button"
                onClick={() => void loadCloudinaryData()}
                disabled={isLoadingCloudinary}
                className="nav-link"
                style={{ cursor: isLoadingCloudinary ? 'wait' : 'pointer' }}
              >
                {isLoadingCloudinary ? 'Loading…' : 'Refresh from API'}
              </button>
            </div>

            {cloudinaryLatest && cloudinaryLatest.status === 'empty' && (
              <p className="status">No events yet. After a successful webhook, results appear here (and in ASI:One via the tool).</p>
            )}

            {cloudinaryLatest && cloudinaryLatest.status === 'ok' && (
              <div className="cloudinary-latest-panel">
                <p className="status">
                  <strong>Event #{cloudinaryLatest.id}</strong> · {cloudinaryLatest.created_at} · status:{' '}
                  <strong>{cloudinaryLatest.result.status}</strong>
                </p>
                <p>
                  <strong>Summary:</strong> {cloudinaryLatest.result.analysis_summary}
                </p>
                {cloudinaryLatest.result.recommended_action && (
                  <p>
                    <strong>Action:</strong> {cloudinaryLatest.result.recommended_action}
                  </p>
                )}
                {cloudinaryLatest.result.risk_labels && cloudinaryLatest.result.risk_labels.length > 0 && (
                  <p>
                    <strong>Labels:</strong> {cloudinaryLatest.result.risk_labels.join(' · ')}
                  </p>
                )}
                {cloudinaryLatest.result.sustainability &&
                  Object.keys(cloudinaryLatest.result.sustainability).length > 0 && (
                    <div className="sustainability-panel">
                      <p>
                        <strong>Sustainability:</strong>
                      </p>
                      {(() => {
                        const s = cloudinaryLatest.result.sustainability as Record<string, unknown>;
                        const water = s.water_saved_liters_estimate;
                        const carbon = s.carbon_kg_co2e_avoided_estimate;
                        const trips = s.avoided_trip_km_estimate;
                        const note = s.waste_reduction_note;
                        const method = s.method;
                        return (
                          <>
                            <p>- Water saved estimate: {water != null ? String(water) : 'n/a'} L</p>
                            <p>- Carbon avoided estimate: {carbon != null ? String(carbon) : 'n/a'} kg CO2e</p>
                            <p>- Travel avoided estimate: {trips != null ? String(trips) : 'n/a'} km</p>
                            {note ? <p>- Waste reduction note: {String(note)}</p> : null}
                            {method ? <p>- Method: {String(method)}</p> : null}
                          </>
                        );
                      })()}
                    </div>
                  )}
                {cloudinaryLatest.result.video_id && (
                  <p>
                    <strong>TwelveLabs video_id:</strong> {cloudinaryLatest.result.video_id}
                  </p>
                )}

                <div className="cloudinary-media-grid">
                  {(
                    [
                      ['Thumbnail', cloudinaryLatest.result.transformed_media_urls?.thumbnail],
                      ['Preview', cloudinaryLatest.result.transformed_media_urls?.preview],
                      ['Overlay (text on image / first frame)', cloudinaryLatest.result.transformed_media_urls?.overlay],
                    ] as const
                  ).map(([label, u]) =>
                    u ? (
                      <figure key={label} className="cloudinary-fig">
                        <figcaption>{label}</figcaption>
                        <a href={u} target="_blank" rel="noreferrer">
                          <img src={u} alt={label} loading="lazy" />
                        </a>
                      </figure>
                    ) : null
                  )}
                </div>
                {cloudinaryLatest.result.transformed_media_urls?.original_secure_url && (
                  <p className="status">
                    <a
                      href={cloudinaryLatest.result.transformed_media_urls.original_secure_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open original in Cloudinary
                    </a>
                  </p>
                )}
              </div>
            )}

            <div className="twelvelabs-log-panel">
              <h3>Recent events (stored)</h3>
              {cloudinaryEvents.length === 0 ? (
                <p>No stored webhook results yet.</p>
              ) : (
                <ul className="cloudinary-event-list">
                  {cloudinaryEvents.map((row) => (
                    <li key={row.id}>
                      <strong>#{row.id}</strong> {row.created_at} — {row.status} — {row.public_id || 'n/a'} (
                      {row.resource_type || '?'})
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>
        )}

        {activePage === 'diseaseAnalysis' && (
          <section className="card disease-analysis-page">
            <div className="card-title-row">
              <h2>Disease Analysis</h2>
              <span className="pill subtle">Drag and drop image upload</span>
            </div>
            <p className="status">
              Upload a crop/leaf image to preview it here. Classification Model will run.
            </p>

            <input
              ref={diseaseFileInputRef}
              type="file"
              accept="image/*"
              className="disease-file-input"
              onChange={handleDiseaseFileInputChange}
            />

            <div
              className={
                isDragOverDiseaseDropzone
                  ? 'disease-dropzone drag-active'
                  : 'disease-dropzone'
              }
              role="button"
              tabIndex={0}
              onClick={() => diseaseFileInputRef.current?.click()}
              onDragOver={(event) => {
                event.preventDefault();
                setIsDragOverDiseaseDropzone(true);
              }}
              onDragLeave={() => setIsDragOverDiseaseDropzone(false)}
              onDrop={handleDiseaseDrop}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  diseaseFileInputRef.current?.click();
                }
              }}
              aria-label="Upload image for disease analysis preview"
            >
              <p>Drag and drop an image here</p>
              <span>or click to browse files</span>
            </div>

            {diseasePreviewUrl && (
              <div className="disease-preview-card">
                <img src={diseasePreviewUrl} alt="Disease analysis upload preview" />
                <p>
                  <strong>Selected file:</strong> {diseasePreviewName}
                </p>
                <button
                  type="button"
                  className="run-decision-btn disease-classify-btn"
                  onClick={() => void handleRunDiseaseClassification()}
                  disabled={isClassifyingDisease}
                >
                  {isClassifyingDisease ? 'Classifying...' : 'Run Classification'}
                </button>
                {diseaseClassificationError && <p className="warning">{diseaseClassificationError}</p>}
                {diseasePredictions.length > 0 && (
                  <div className="disease-predictions">
                    <h3>Predictions</h3>
                    <ul>
                      {diseasePredictions.map((item) => (
                        <li key={`${item.rank}-${item.label}`}>
                          <span>{item.rank}. {item.label.replace(/_/g, ' ')}</span>
                          <strong>{(item.confidence * 100).toFixed(1)}%</strong>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </section>
        )}

        {activePage === 'irrigator' && (
          <section className="card irrigator-page">
            <div className="card-title-row">
              <h2>Irrigation Agent (ET-based)</h2>
              <span className="pill subtle">Standalone irrigator UI</span>
            </div>
            <p className="status">
              Enter sensor and location inputs, then run the irrigator to get action, amount, and reason.
            </p>

            <div className="grid irrigator-form-grid">
              <label>
                City (optional if lat/lon are set)
                <input
                  type="text"
                  value={irrigatorForm.city}
                  onChange={(event) => setIrrigatorForm((prev) => ({ ...prev, city: event.target.value }))}
                  placeholder="Toronto"
                />
              </label>
              <label>
                Latitude
                <input
                  type="number"
                  value={irrigatorForm.latitude}
                  onChange={(event) =>
                    setIrrigatorForm((prev) => ({ ...prev, latitude: event.target.value }))
                  }
                  placeholder="43.65"
                />
              </label>
              <label>
                Longitude
                <input
                  type="number"
                  value={irrigatorForm.longitude}
                  onChange={(event) =>
                    setIrrigatorForm((prev) => ({ ...prev, longitude: event.target.value }))
                  }
                  placeholder="-79.38"
                />
              </label>
              <label>
                Temperature (C)
                <input
                  type="number"
                  value={irrigatorForm.temperature}
                  onChange={(event) =>
                    setIrrigatorForm((prev) => ({ ...prev, temperature: Number(event.target.value) }))
                  }
                />
              </label>
              <label>
                Moisture (%)
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={irrigatorForm.moisture}
                  onChange={(event) =>
                    setIrrigatorForm((prev) => ({ ...prev, moisture: Number(event.target.value) }))
                  }
                />
              </label>
              <label>
                Light
                <input
                  type="number"
                  value={irrigatorForm.light}
                  onChange={(event) =>
                    setIrrigatorForm((prev) => ({ ...prev, light: Number(event.target.value) }))
                  }
                />
              </label>
              <label>
                Air quality (%)
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={irrigatorForm.airQuality}
                  onChange={(event) =>
                    setIrrigatorForm((prev) => ({ ...prev, airQuality: Number(event.target.value) }))
                  }
                />
              </label>
            </div>

            <button
              type="button"
              className="run-decision-btn"
              onClick={() => void runIrrigator()}
              disabled={isRunningIrrigator}
            >
              {isRunningIrrigator ? 'Running irrigator...' : 'Run Irrigator'}
            </button>

            {irrigatorError && <p className="warning">{irrigatorError}</p>}

            {irrigatorResult && (
              <div className="agent-output">
                <p>
                  <strong>Weather:</strong> {irrigatorResult.weatherSummary}
                </p>
                <p>
                  <strong>Water need index:</strong> {irrigatorResult.waterNeed.toFixed(4)}
                </p>
                <p>
                  <strong>Action:</strong> {irrigatorResult.action}
                </p>
                <p>
                  <strong>Amount:</strong> {irrigatorResult.amountMl} ml
                </p>
                <p>{irrigatorResult.reason}</p>
              </div>
            )}

            <div className="irrigator-chat-widget">
              <h3>Irrigator Chat</h3>
              <div className="irrigator-chat-log">
                {irrigatorChat.length === 0 ? (
                  <p className="status">No messages yet. Run irrigator and ask follow-up questions.</p>
                ) : (
                  irrigatorChat.map((message, index) => (
                    <p key={`${message.role}-${index}`} className={message.role === 'agent' ? 'chat-bubble agent' : 'chat-bubble user'}>
                      <strong>{message.role === 'agent' ? 'Irrigator' : 'You'}:</strong> {message.text}
                    </p>
                  ))
                )}
              </div>
              <div className="irrigator-chat-input-row">
                <input
                  type="text"
                  value={irrigatorChatInput}
                  onChange={(event) => setIrrigatorChatInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      handleIrrigatorChatSend();
                    }
                  }}
                  placeholder="Ask: why this decision, rain impact, amount..."
                />
                <button type="button" onClick={handleIrrigatorChatSend}>
                  Send
                </button>
              </div>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

export default App;