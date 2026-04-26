# Data Contracts

## Capture Event (Pi -> Server)

```json
{
  "scan_id": "scan-001",
  "timestamp": "2026-04-25T21:00:00Z",
  "gps_or_row_id": "row-12",
  "image_uri": "https://storage.local/scans/scan-001.jpg",
  "sensor_values": {
    "moisture_pct": 32.1,
    "air_quality_index": 72,
    "light_lux": 14500,
    "temperature_c": 29.3
  },
  "metadata": {
    "device_id": "pi-5-robot-1"
  }
}
```

## Vision Contract (VLM Output)

```json
{
  "disease_or_stress_label": "powdery_mildew",
  "severity": "high",
  "confidence": 0.79,
  "visual_evidence": ["white powder spots", "leaf edge distortion"],
  "top_k": [
    {"powdery_mildew": 0.79},
    {"bacterial_spot": 0.63},
    {"healthy_leaf": 0.54}
  ]
}
```

## Fusion Contract (Vision + Sensor)

```json
{
  "scan_id": "scan-001",
  "risk_score": 0.83,
  "irrigation_flag": false,
  "fertilizer_flag": false,
  "pest_flag": false,
  "severity": "high",
  "rationale": [
    "Leaf stress likely due to high ambient temperature."
  ],
  "vlm": {},
  "sensors": {}
}
```
