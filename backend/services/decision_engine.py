from __future__ import annotations

from backend.models.contracts import (
    CropStage,
    DiagnosisResult,
    ImageSignal,
    IrrigationResult,
    SensorSnapshot,
)


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def run_leaf_diagnosis(signal: ImageSignal | None) -> DiagnosisResult:
    if signal is None:
        return DiagnosisResult(
            disease="no_image_signal",
            confidence=0.35,
            urgency="low",
            actions=["Upload a leaf image to run disease analysis."],
        )

    public_id = signal.public_id.lower()
    file_format = signal.format.lower()
    hash_hint = signal.bytes % 17
    confidence_base = 0.62 + ((hash_hint % 18) / 100)

    if "spot" in public_id or "blight" in public_id:
        return DiagnosisResult(
            disease="early_leaf_spot",
            confidence=clamp(confidence_base + 0.14, 0.70, 0.95),
            urgency="high",
            actions=[
                "Isolate affected plants and avoid overhead watering.",
                "Remove heavily infected leaves and sanitize tools.",
                "Apply a minimal organic copper treatment.",
            ],
        )

    if "yellow" in public_id or "chlorosis" in public_id:
        return DiagnosisResult(
            disease="possible_nutrient_deficiency",
            confidence=clamp(confidence_base + 0.07, 0.68, 0.90),
            urgency="medium",
            actions=[
                "Check soil pH and move toward crop-specific range.",
                "Apply balanced nutrients or foliar micronutrients.",
                "Capture another image in 3 to 5 days.",
            ],
        )

    if file_format == "png" and signal.width > signal.height:
        return DiagnosisResult(
            disease="possible_pest_damage",
            confidence=clamp(confidence_base + 0.05, 0.65, 0.88),
            urgency="medium",
            actions=[
                "Inspect leaf undersides for pests or eggs.",
                "Use neem oil or biological controls at dusk.",
                "Repeat scouting daily for one week.",
            ],
        )

    return DiagnosisResult(
        disease="no_strong_disease_signal",
        confidence=clamp(confidence_base, 0.60, 0.86),
        urgency="low",
        actions=[
            "Continue monitoring and capture another image in 48 hours.",
            "Keep airflow high and avoid prolonged leaf wetness.",
            "Track color, spots, and curling progression.",
        ],
    )


def get_irrigation_recommendation(
    sensors: SensorSnapshot,
    stage: CropStage,
    rain_chance: float,
) -> IrrigationResult:
    stage_factor = 0.75 if stage == "seedling" else 1.0 if stage == "vegetative" else 1.2
    dryness = clamp((55 - sensors.soil_moisture) / 20, 0, 2.2)
    heat_boost = clamp((sensors.temperature_c - 28) / 10, 0, 1)
    humidity_relief = clamp((70 - sensors.humidity) / 30, 0, 1)
    rain_relief = clamp(rain_chance / 100, 0, 0.8)

    liters = clamp((1.4 + dryness + heat_boost + humidity_relief - rain_relief) * stage_factor, 0.3, 3.6)

    if sensors.soil_moisture < 32 and rain_chance < 40:
        return IrrigationResult(
            action="water_now",
            liters=round(liters, 1),
            urgency="high",
            rationale="Soil moisture is below the safe band and rain relief is low.",
        )

    if 32 <= sensors.soil_moisture <= 58 and rain_chance >= 55:
        return IrrigationResult(
            action="no_watering",
            liters=0,
            urgency="low",
            rationale="Current moisture is acceptable and forecasted rain can cover demand.",
        )

    return IrrigationResult(
        action="light_watering",
        liters=round(liters * 0.6, 1),
        urgency="medium",
        rationale="Run a short cycle and re-check soil moisture in 90 minutes.",
    )
