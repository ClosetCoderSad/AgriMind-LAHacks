from typing import Literal

from pydantic import BaseModel, Field


CropStage = Literal["seedling", "vegetative", "flowering"]
UrgencyLevel = Literal["low", "medium", "high"]
ActionType = Literal["water_now", "light_watering", "no_watering"]


class SensorSnapshot(BaseModel):
    soil_moisture: float = Field(ge=0, le=100)
    temperature_c: float = Field(ge=-20, le=80)
    humidity: float = Field(ge=0, le=100)
    light_lux: float = Field(ge=0, le=200000)
    ph: float = Field(ge=0, le=14)


class ImageSignal(BaseModel):
    public_id: str
    format: str
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    bytes: int = Field(ge=1)
    resource_type: str = "image"
    secure_url: str | None = None


class DiagnosisResult(BaseModel):
    disease: str
    confidence: float = Field(ge=0, le=1)
    urgency: UrgencyLevel
    actions: list[str]


class IrrigationResult(BaseModel):
    action: ActionType
    liters: float = Field(ge=0)
    urgency: UrgencyLevel
    rationale: str


class SustainabilityImpact(BaseModel):
    water_saved_ml: int = Field(ge=0)
    risk_level: UrgencyLevel
    fertilizer_avoided: bool


class DecisionRequest(BaseModel):
    sensors: SensorSnapshot
    crop_stage: CropStage
    rain_chance: float = Field(ge=0, le=100)
    image: ImageSignal | None = None
    plant_type: str = "tomato"


class HealthAgentOutput(BaseModel):
    disease: str
    severity: UrgencyLevel
    diagnosis_confidence: float = Field(ge=0, le=1)
    explanation: str
    visual_history_url: str | None = None
    twelvelabs_status: str | None = None
    twelvelabs_index_id: str | None = None
    twelvelabs_asset_id: str | None = None
    twelvelabs_indexed_asset_id: str | None = None
    twelvelabs_video_id: str | None = None
    twelvelabs_stream_url: str | None = None
    twelvelabs_search_reference: str | None = None
    twelvelabs_summary: str | None = None


class DecisionResponse(BaseModel):
    action: ActionType
    disease: str
    recommendation: str
    impact: SustainabilityImpact
    diagnosis: DiagnosisResult
    irrigation: IrrigationResult
    health: HealthAgentOutput


class ExplainRequest(BaseModel):
    decision: DecisionResponse


class ExplainResponse(BaseModel):
    explanation: str
