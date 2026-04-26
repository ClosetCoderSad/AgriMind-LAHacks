from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class SensorValues(BaseModel):
    moisture_pct: float = Field(ge=0, le=100)
    air_quality_index: float = Field(ge=0)
    light_lux: float = Field(ge=0)
    temperature_c: float = Field(ge=-40, le=85)


class CaptureEvent(BaseModel):
    scan_id: str
    timestamp: datetime
    gps_or_row_id: str
    image_uri: HttpUrl | str
    sensor_values: SensorValues
    metadata: Dict[str, str] = Field(default_factory=dict)


class VLMOutput(BaseModel):
    disease_or_stress_label: str
    severity: Severity
    confidence: float = Field(ge=0, le=1)
    visual_evidence: List[str] = Field(default_factory=list)
    top_k: List[Dict[str, float]] = Field(default_factory=list)


class FusionOutput(BaseModel):
    scan_id: str
    risk_score: float = Field(ge=0, le=1)
    irrigation_flag: bool
    fertilizer_flag: bool
    pest_flag: bool
    severity: Severity
    rationale: List[str]
    vlm: VLMOutput
    sensors: SensorValues


class GemmaAdvice(BaseModel):
    scan_id: str
    summary: str
    confidence_band: str
    urgency: str
    interventions: List[str]
    monitor_after_hours: int
    notes: Optional[str] = None
