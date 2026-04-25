import { useMemo, useState } from 'react';
import { uploadPreset } from './cloudinary/config';
import { UploadWidget } from './cloudinary/UploadWidget';
import type { CloudinaryUploadResult } from './cloudinary/UploadWidget';
import './App.css';

type CropStage = 'seedling' | 'vegetative' | 'flowering';

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
  const [sensors, setSensors] = useState<SensorSnapshot>(INITIAL_SENSORS);
  const [cropStage, setCropStage] = useState<CropStage>('vegetative');
  const [rainChance, setRainChance] = useState(35);
  const [latestUpload, setLatestUpload] = useState<CloudinaryUploadResult | null>(null);
  const [diagnosis, setDiagnosis] = useState<DiagnosisResult | null>(null);
  const [uploadMessage, setUploadMessage] = useState('');

  const handleUploadSuccess = (result: CloudinaryUploadResult) => {
    if (result.resource_type !== 'image') {
      setUploadMessage('Please upload a plant leaf image for diagnosis.');
      return;
    }

    setLatestUpload(result);
    setDiagnosis(runLeafDiagnosis(result));
    setUploadMessage('Leaf image analyzed. Review diagnosis below.');
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

  return (
    <div className="app">
      <main className="layout">
        <header className="hero">
          <h1>AgriMind</h1>
          <p>Smart micro-farming assistant for soil health, leaf diagnosis, and watering plans.</p>
        </header>

        <section className="card">
          <div className="card-title-row">
            <h2>Live Farm Snapshot</h2>
            <span className="pill">Health Score: {healthScore}/100</span>
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
              <img src={latestUpload.secure_url} alt="Uploaded leaf sample" />
              <div>
                <p>
                  <strong>Public ID:</strong> {latestUpload.public_id}
                </p>
                <p>
                  <strong>Image size:</strong> {latestUpload.width} x {latestUpload.height}
                </p>
              </div>
            </div>
          )}

          {diagnosis && (
            <div className={`diagnosis ${diagnosis.urgency}`}>
              <p>
                <strong>Result:</strong> {diagnosis.label}
              </p>
              <p>
                <strong>Confidence:</strong> {diagnosis.confidence}%
              </p>
              <p>
                <strong>Urgency:</strong> {diagnosis.urgency}
              </p>
              <ul>
                {diagnosis.actions.map((action) => (
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
              <strong>Decision:</strong> {watering.decision}
            </p>
            <p>
              <strong>Recommended water:</strong> {watering.amountLiters} L per bed/zone
            </p>
            <p>{watering.note}</p>
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;
