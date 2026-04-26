from __future__ import annotations

from agrimind.schemas import CaptureEvent, FusionOutput, Severity, VLMOutput


def _severity_to_score(severity: Severity) -> float:
    return {
        Severity.low: 0.25,
        Severity.medium: 0.5,
        Severity.high: 0.75,
        Severity.critical: 0.95,
    }[severity]


def fuse_sensor_and_vision(capture: CaptureEvent, vlm_output: VLMOutput) -> FusionOutput:
    """Fuse vision prediction with sensor anomalies into a normalized risk score."""
    sv = capture.sensor_values
    rationale: list[str] = []

    base = _severity_to_score(vlm_output.severity) * 0.6 + vlm_output.confidence * 0.3

    moisture_risk = 0.0
    if sv.moisture_pct < 25:
        moisture_risk = 0.2
        rationale.append("Soil moisture is below healthy threshold.")
    elif sv.moisture_pct > 80:
        moisture_risk = 0.12
        rationale.append("Soil moisture is very high; fungal risk may increase.")

    heat_risk = 0.0
    if sv.temperature_c > 33:
        heat_risk = 0.14
        rationale.append("Leaf stress likely due to high ambient temperature.")

    light_risk = 0.0
    if sv.light_lux < 8000:
        light_risk = 0.08
        rationale.append("Low light may suppress growth and mask disease cues.")

    air_risk = 0.0
    if sv.air_quality_index > 150:
        air_risk = 0.1
        rationale.append("Poor air quality may correlate with crop stress.")

    risk_score = min(1.0, base + moisture_risk + heat_risk + light_risk + air_risk)
    severity = (
        Severity.critical
        if risk_score >= 0.9
        else Severity.high
        if risk_score >= 0.7
        else Severity.medium
        if risk_score >= 0.45
        else Severity.low
    )

    irrigation_flag = sv.moisture_pct < 28
    fertilizer_flag = "deficiency" in vlm_output.disease_or_stress_label.lower()
    pest_flag = any("pest" in token.lower() for token in vlm_output.visual_evidence)

    if not rationale:
        rationale.append("Vision model confidence and severity are within normal range.")

    return FusionOutput(
        scan_id=capture.scan_id,
        risk_score=risk_score,
        irrigation_flag=irrigation_flag,
        fertilizer_flag=fertilizer_flag,
        pest_flag=pest_flag,
        severity=severity,
        rationale=rationale,
        vlm=vlm_output,
        sensors=sv,
    )
