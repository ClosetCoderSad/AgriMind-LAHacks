import type { CloudinaryUploadResult } from '../cloudinary/UploadWidget';

export type CropStage = 'seedling' | 'vegetative' | 'flowering';

export interface SensorSnapshotApi {
  soil_moisture: number;
  temperature_c: number;
  humidity: number;
  light_lux: number;
  ph: number;
}

export interface DiagnosisResultApi {
  disease: string;
  confidence: number;
  urgency: 'low' | 'medium' | 'high';
  actions: string[];
}

export interface IrrigationResultApi {
  action: 'water_now' | 'light_watering' | 'no_watering';
  liters: number;
  urgency: 'low' | 'medium' | 'high';
  rationale: string;
}

export interface DecisionResponseApi {
  action: 'water_now' | 'light_watering' | 'no_watering';
  disease: string;
  recommendation: string;
  impact: {
    water_saved_ml: number;
    risk_level: 'low' | 'medium' | 'high';
    fertilizer_avoided: boolean;
  };
  diagnosis: DiagnosisResultApi;
  irrigation: IrrigationResultApi;
  health: {
    disease: string;
    severity: 'low' | 'medium' | 'high';
    diagnosis_confidence: number;
    explanation: string;
    visual_history_url?: string | null;
    twelvelabs_status?: string | null;
    twelvelabs_index_id?: string | null;
    twelvelabs_asset_id?: string | null;
    twelvelabs_indexed_asset_id?: string | null;
    twelvelabs_video_id?: string | null;
    twelvelabs_stream_url?: string | null;
    twelvelabs_search_reference?: string | null;
    twelvelabs_summary?: string | null;
  };
}

export interface TwelvelabsIngestionResultApi {
  status: string;
  summary: string;
  index_id?: string | null;
  asset_id?: string | null;
  indexed_asset_id?: string | null;
  video_id?: string | null;
  stream_url?: string | null;
  search_reference?: string | null;
  error?: string | null;
}

export interface TwelvelabsHistoryItemApi {
  created_at: string;
  source_key?: string | null;
  status: string;
  index_id?: string | null;
  asset_id?: string | null;
  indexed_asset_id?: string | null;
  video_id?: string | null;
  stream_url?: string | null;
  search_reference?: string | null;
  error?: string | null;
}

export interface TwelvelabsIndexVideoApi {
  video_id: string;
  index_id: string;
  filename?: string | null;
  duration?: number | null;
  created_at?: string | null;
  stream_url?: string | null;
}

export interface TwelvelabsTextResultApi {
  status: string;
  text?: string | null;
  error?: string | null;
}

interface DecisionRequestApi {
  sensors: SensorSnapshotApi;
  crop_stage: CropStage;
  rain_chance: number;
  image?: {
    public_id: string;
    format: string;
    width: number;
    height: number;
    bytes: number;
    resource_type: string;
    secure_url: string;
  };
  plant_type?: string;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status}: ${body}`);
  }

  return response.json() as Promise<T>;
}

function mapImageSignal(upload: CloudinaryUploadResult | null) {
  if (!upload) {
    return undefined;
  }

  return {
    public_id: upload.public_id,
    format: upload.format,
    width: upload.width,
    height: upload.height,
    bytes: upload.bytes,
    resource_type: upload.resource_type,
    secure_url: upload.secure_url,
  };
}

export function mapSensorsToApi(sensors: {
  soilMoisture: number;
  temperatureC: number;
  humidity: number;
  lightLux: number;
  ph: number;
}): SensorSnapshotApi {
  return {
    soil_moisture: sensors.soilMoisture,
    temperature_c: sensors.temperatureC,
    humidity: sensors.humidity,
    light_lux: sensors.lightLux,
    ph: sensors.ph,
  };
}

export async function getAgentDecision(input: {
  sensors: SensorSnapshotApi;
  cropStage: CropStage;
  rainChance: number;
  latestUpload: CloudinaryUploadResult | null;
  plantType?: string;
}): Promise<DecisionResponseApi> {
  const payload: DecisionRequestApi = {
    sensors: input.sensors,
    crop_stage: input.cropStage,
    rain_chance: input.rainChance,
    plant_type: input.plantType || 'tomato',
  };

  const image = mapImageSignal(input.latestUpload);
  if (image) {
    payload.image = image;
  }

  return fetchJson<DecisionResponseApi>('/api/decision', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function getDecisionExplanation(decision: DecisionResponseApi): Promise<string> {
  const data = await fetchJson<{ explanation: string }>('/api/explain', {
    method: 'POST',
    body: JSON.stringify({ decision }),
  });
  return data.explanation;
}

export async function ingestVideoToTwelvelabs(input: {
  videoUrl: string;
  sourceKey?: string;
}): Promise<TwelvelabsIngestionResultApi> {
  return fetchJson<TwelvelabsIngestionResultApi>('/api/health/ingest-video', {
    method: 'POST',
    body: JSON.stringify({
      video_url: input.videoUrl,
      source_key: input.sourceKey,
    }),
  });
}

export async function getTwelvelabsHistory(limit = 20): Promise<TwelvelabsHistoryItemApi[]> {
  return fetchJson<TwelvelabsHistoryItemApi[]>(`/api/twelvelabs/history?limit=${limit}`);
}

export async function getTwelvelabsIndexVideos(input?: {
  indexId?: string;
  limit?: number;
}): Promise<{ videos: TwelvelabsIndexVideoApi[]; error?: string | null }> {
  const limit = input?.limit ?? 20;
  const query = input?.indexId ? `?index_id=${encodeURIComponent(input.indexId)}&limit=${limit}` : `?limit=${limit}`;
  return fetchJson<{ videos: TwelvelabsIndexVideoApi[]; error?: string | null }>(`/api/twelvelabs/videos${query}`);
}

export async function summarizeIndexedVideo(input: {
  videoId: string;
  summaryType?: 'summary' | 'chapter' | 'highlight';
  prompt?: string;
}): Promise<TwelvelabsTextResultApi> {
  return fetchJson<TwelvelabsTextResultApi>('/api/twelvelabs/summarize', {
    method: 'POST',
    body: JSON.stringify({
      video_id: input.videoId,
      summary_type: input.summaryType || 'summary',
      prompt: input.prompt || undefined,
    }),
  });
}

export async function askIndexedVideoQuestion(input: {
  videoId: string;
  question: string;
}): Promise<TwelvelabsTextResultApi> {
  return fetchJson<TwelvelabsTextResultApi>('/api/twelvelabs/qna', {
    method: 'POST',
    body: JSON.stringify({
      video_id: input.videoId,
      question: input.question,
    }),
  });
}
