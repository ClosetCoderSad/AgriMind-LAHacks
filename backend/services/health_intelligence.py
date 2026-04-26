from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from backend.models.contracts import DiagnosisResult, HealthAgentOutput, ImageSignal
from backend.services.twelvelabs_client import TwelveLabsClientService


def _severity_from_diagnosis(disease: str, confidence: float) -> str:
    if disease == "early_leaf_spot" and confidence >= 0.85:
        return "high"
    if confidence >= 0.75 or disease in {"possible_nutrient_deficiency", "possible_pest_damage"}:
        return "medium"
    return "low"


def _build_cloudinary_history_url(image: ImageSignal | None) -> str | None:
    if image is None:
        return None

    cloud_name = os.getenv("VITE_CLOUDINARY_CLOUD_NAME") or os.getenv("CLOUDINARY_CLOUD_NAME")
    if not cloud_name:
        return None

    public_id = image.public_id
    return (
        f"https://res.cloudinary.com/{cloud_name}/image/upload/"
        f"f_auto,q_auto,w_900/{public_id}.{image.format}"
    )


def _build_cloudinary_video_url(image: ImageSignal | None) -> str | None:
    if image is None:
        return None

    if image.secure_url and image.resource_type == "video":
        return image.secure_url

    cloud_name = os.getenv("VITE_CLOUDINARY_CLOUD_NAME") or os.getenv("CLOUDINARY_CLOUD_NAME")
    if not cloud_name:
        return None

    if image.resource_type != "video":
        return None

    return (
        f"https://res.cloudinary.com/{cloud_name}/video/upload/"
        f"f_auto,q_auto/{image.public_id}.mp4"
    )


def _fallback_gemma_explanation(
    disease: str,
    confidence: float,
    plant_type: str,
    severity: str,
) -> str:
    if disease == "early_leaf_spot":
        return (
            f"Early-stage leaf spot is likely driven by fungal pressure under humid conditions in {plant_type}. "
            f"Confidence is {confidence:.2f}, with {severity} severity right now. Improve airflow and avoid overhead watering."
        )

    if disease == "possible_nutrient_deficiency":
        return (
            f"Leaf color pattern suggests nutrient stress in {plant_type}. "
            f"Confidence is {confidence:.2f}, with {severity} severity. Check pH and rebalance nitrogen and iron inputs."
        )

    if disease == "possible_pest_damage":
        return (
            f"Visual pattern indicates potential pest feeding damage in {plant_type}. "
            f"Confidence is {confidence:.2f}, with {severity} severity. Inspect leaf undersides and apply targeted biological control."
        )

    return (
        f"No strong disease signature was detected for {plant_type}. "
        f"Confidence is {confidence:.2f}, with {severity} severity. Continue monitoring with periodic image capture."
    )


def _call_gemma_reasoning(
    disease: str,
    confidence: float,
    plant_type: str,
    severity: str,
) -> str:
    api_url = os.getenv("GEMMA_API_URL", "").strip()
    api_key = os.getenv("GEMMA_API_KEY", "").strip()

    if not api_url:
        return _fallback_gemma_explanation(disease, confidence, plant_type, severity)

    payload = {
        "tool": "gemma.generate",
        "input": {
            "disease": disease,
            "confidence": confidence,
            "plant_type": plant_type,
            "severity": severity,
        },
    }

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = Request(api_url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")

    try:
        with urlopen(request, timeout=8) as response:
            content: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        return str(content.get("output") or content.get("text") or content.get("explanation") or "") or _fallback_gemma_explanation(
            disease, confidence, plant_type, severity
        )
    except (TimeoutError, URLError, json.JSONDecodeError):
        return _fallback_gemma_explanation(disease, confidence, plant_type, severity)


def _optional_twelvelabs_summary(
    disease: str,
    severity: str,
    twelvelabs_status: str | None,
    search_reference: str | None,
) -> str | None:
    enabled = os.getenv("TWELVELABS_ENABLED", "false").lower() == "true"
    if not enabled:
        return None

    if not twelvelabs_status:
        return "TwelveLabs hook enabled, but ingestion did not run yet."

    return (
        f"TwelveLabs ingestion status={twelvelabs_status} for disease={disease}, severity={severity}. "
        f"Search reference: {search_reference or 'pending'}"
    )


def build_health_agent_output(
    diagnosis: DiagnosisResult,
    image: ImageSignal | None,
    plant_type: str,
    ingestion_store: Any | None = None,
) -> HealthAgentOutput:
    severity = _severity_from_diagnosis(diagnosis.disease, diagnosis.confidence)
    visual_history_url = _build_cloudinary_history_url(image)
    twelvelabs_video_url = _build_cloudinary_video_url(image)
    explanation = _call_gemma_reasoning(
        disease=diagnosis.disease,
        confidence=diagnosis.confidence,
        plant_type=plant_type,
        severity=severity,
    )

    twelvelabs_result = TwelveLabsClientService().ingest_video_url(twelvelabs_video_url or "")

    if ingestion_store and hasattr(ingestion_store, "save_twelvelabs_ingestion"):
        ingestion_store.save_twelvelabs_ingestion(
            {
                "source_key": image.public_id if image else None,
                "status": twelvelabs_result.status,
                "index_id": twelvelabs_result.index_id,
                "asset_id": twelvelabs_result.asset_id,
                "indexed_asset_id": twelvelabs_result.indexed_asset_id,
                "video_id": twelvelabs_result.video_id,
                "stream_url": twelvelabs_result.stream_url,
                "search_reference": twelvelabs_result.search_reference,
                "error": twelvelabs_result.error,
            }
        )

    twelvelabs_summary = _optional_twelvelabs_summary(
        disease=diagnosis.disease,
        severity=severity,
        twelvelabs_status=twelvelabs_result.status,
        search_reference=twelvelabs_result.search_reference,
    )

    return HealthAgentOutput(
        disease=diagnosis.disease,
        severity=severity,
        diagnosis_confidence=diagnosis.confidence,
        explanation=explanation,
        visual_history_url=visual_history_url,
        twelvelabs_status=twelvelabs_result.status,
        twelvelabs_index_id=twelvelabs_result.index_id,
        twelvelabs_asset_id=twelvelabs_result.asset_id,
        twelvelabs_indexed_asset_id=twelvelabs_result.indexed_asset_id,
        twelvelabs_video_id=twelvelabs_result.video_id,
        twelvelabs_stream_url=twelvelabs_result.stream_url,
        twelvelabs_search_reference=twelvelabs_result.search_reference,
        twelvelabs_summary=twelvelabs_summary,
    )
