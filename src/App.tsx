import { useCallback, useEffect, useMemo, useState } from 'react';
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

type AppPage = 'dashboard' | 'twelvelabs' | 'cloudinary';

const hasUploadPreset = Boolean(uploadPreset);
const INITIAL_SENSORS: SensorSnapshot = {
  soilMoisture: 46,
  temperatureC: 28,
  humidity: 63,
  lightLux: 12000,
  ph: 6.7,
};

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

function App() {
  const getPageFromPath = (): AppPage => {
    const p = window.location.pathname;
    if (p === '/twelvelabs' || p.startsWith('/twelvelabs/')) {
      return 'twelvelabs';
    }
    if (p === '/cloudinary' || p.startsWith('/cloudinary/')) {
      return 'cloudinary';
    }
    return 'dashboard';
  };

  const [activePage, setActivePage] = useState<AppPage>(() => getPageFromPath());
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
  const [isLoadingIndexVideos, setIsLoadingIndexVideos] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [uploadMessage, setUploadMessage] = useState('');
  const [cloudinaryMessage, setCloudinaryMessage] = useState('');
  const [cloudinaryLatest, setCloudinaryLatest] = useState<CloudinaryLatestResponseApi | null>(null);
  const [cloudinaryEvents, setCloudinaryEvents] = useState<CloudinaryEventRowApi[]>([]);
  const [isLoadingCloudinary, setIsLoadingCloudinary] = useState(false);
  const [cloudinaryLastUpload, setCloudinaryLastUpload] = useState<CloudinaryUploadResult | null>(null);
  const [isRunningLocalCloudinary, setIsRunningLocalCloudinary] = useState(false);

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
      const result = await ingestVideoToTwelvelabs({
        videoUrl: videoUrlInput.trim(),
        sourceKey: latestUpload?.public_id,
      });
      setLastIngestionResult(result);
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
      setActivePage(getPageFromPath());
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const navigateToPage = (page: AppPage) => {
    const targetPath =
      page === 'twelvelabs' ? '/twelvelabs' : page === 'cloudinary' ? '/cloudinary' : '/';
    if (window.location.pathname !== targetPath) {
      window.history.pushState({}, '', targetPath);
    }
    setActivePage(page);
  };

  const handleUploadError = (error: Error) => {
    setUploadMessage(`Upload failed: ${error.message}`);
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

  return (
    <div className="app">
      <main className="layout">
        <header className="hero">
          <h1>AgriMind</h1>
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
        </nav>

        {activePage === 'dashboard' && (
          <>
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
          </>
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
                            <p>- Water saved estimate: {water ?? 'n/a'} L</p>
                            <p>- Carbon avoided estimate: {carbon ?? 'n/a'} kg CO2e</p>
                            <p>- Travel avoided estimate: {trips ?? 'n/a'} km</p>
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
      </main>
    </div>
  );
}

export default App;
