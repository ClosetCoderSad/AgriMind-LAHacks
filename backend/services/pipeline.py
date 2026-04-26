from typing import Any

from backend.models.contracts import DecisionRequest, DecisionResponse, SustainabilityImpact
from backend.services.decision_engine import get_irrigation_recommendation, run_leaf_diagnosis
from backend.services.health_intelligence import build_health_agent_output



def run_agri_pipeline(request: DecisionRequest, ingestion_store: Any | None = None) -> DecisionResponse:
    diagnosis = run_leaf_diagnosis(request.image)
    health = build_health_agent_output(
        diagnosis=diagnosis,
        image=request.image,
        plant_type=request.plant_type,
        ingestion_store=ingestion_store,
    )

    irrigation = get_irrigation_recommendation(
        sensors=request.sensors,
        stage=request.crop_stage,
        rain_chance=request.rain_chance,
    )

    base_water_ml = 500
    action_multiplier = {
        "no_watering": 1.0,
        "light_watering": 0.5,
        "water_now": 0.0,
    }[irrigation.action]

    impact = SustainabilityImpact(
        water_saved_ml=int(base_water_ml * action_multiplier),
        risk_level=health.severity,
        fertilizer_avoided=health.severity in {"low", "medium"},
    )

    recommendation = diagnosis.actions[0] if diagnosis.actions else "Continue monitoring conditions."

    return DecisionResponse(
        action=irrigation.action,
        disease=diagnosis.disease,
        recommendation=recommendation,
        impact=impact,
        diagnosis=diagnosis,
        irrigation=irrigation,
        health=health,
    )
