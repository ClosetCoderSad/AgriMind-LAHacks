"""
Run AgriMind analysis after a Cloudinary upload notification (webhook).
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from backend.models.cloudinary_contracts import (
    CloudinaryAnalysisOutput,
    NormalizedMediaEvent,
    TransformedMediaUrls,
)
from backend.services.cloudinary_client import (
    build_transformation_urls,
    extract_cloud_name_from_url,
    normalize_to_media_event,
    parse_notification_body,
    verify_notification_signature,
)
from backend.services.twelvelabs_client import TwelveLabsClientService

STRUCTURED_CROP_SUMMARY_PROMPT = """
You are an agricultural AI expert.

Analyze this farm video and return ONLY valid JSON:

{
  "disease": "name or none",
  "severity": "low | medium | high",
  "confidence": 0-100,
  "key_observations": ["..."],
  "recommended_actions": ["..."],
  "irrigation_adjustment": "increase | decrease | no_change"
}
"""


def _estimate_sustainability_metrics(
    event: NormalizedMediaEvent,
    is_video: bool,
    risk_level: str,
) -> dict[str, Any]:
    """
    Lightweight, explainable sustainability estimates for demo storytelling.
    These are intentionally conservative heuristics (not audited carbon accounting).
    """
    # Assume one avoided on-site inspection trip when remote visual checks are sufficient.
    avoided_trip_km = 6 if is_video else 4
    # Rough passenger-vehicle emission factor (~0.19 kg CO2e / km).
    carbon_kg_co2e_avoided = round(avoided_trip_km * 0.19, 2)

    # Small water-saving estimate from faster intervention loops.
    water_saved_liters = 35 if risk_level == "HIGH" else 18 if risk_level == "MEDIUM" else 8

    # Waste-reduction message scales with richer media type.
    waste_note = (
        "Video-backed remote checks help avoid reactive over-application of water and inputs."
        if is_video
        else "Image-based remote checks reduce unnecessary field trips and duplicate inspections."
    )

    return {
        "water_saved_liters_estimate": water_saved_liters,
        "carbon_kg_co2e_avoided_estimate": carbon_kg_co2e_avoided,
        "avoided_trip_km_estimate": avoided_trip_km,
        "waste_reduction_note": waste_note,
        "method": "heuristic_estimate_for_demo",
    }


def _image_risk_labels(event: NormalizedMediaEvent, risk_level: str) -> list[str]:
    labels: list[str] = [
        f"resource:{event.resource_type or 'image'}",
        f"risk:{risk_level.lower()}",
        "mode:remote_monitoring",
    ]

    # Add optional operational/progression metadata when available.
    if event.farm_id:
        labels.append(f"farm:{event.farm_id}")
    if event.plot_id:
        labels.append(f"plot:{event.plot_id}")
    if event.plant_id:
        labels.append(f"plant:{event.plant_id}")
    if event.day_index:
        labels.append(f"day_index:{event.day_index}")

    tags = [t.strip().lower() for t in event.tags if str(t).strip()]
    labels.extend([f"tag:{t}" for t in tags[:6]])
    return labels[:20]


def _compact_overlay_labels(labels: list[str]) -> str:
    # Keep overlay text short and parser-safe.
    short = [lbl.replace(":", " ").replace(",", " ").strip() for lbl in labels[:3] if lbl.strip()]
    return " ".join(short)


def _overlay_metrics_badge(sustainability: dict[str, Any]) -> str:
    water = sustainability.get("water_saved_liters_estimate")
    carbon = sustainability.get("carbon_kg_co2e_avoided_estimate")
    water_s = f"W{int(float(water))}L" if water is not None else "Wna"
    if carbon is not None:
        carbon_v = f"{float(carbon):.2f}".replace(".", "_")
        carbon_s = f"C{carbon_v}kg"
    else:
        carbon_s = "Cna"
    return f"{water_s} {carbon_s}"


def _risk_from_event(event: NormalizedMediaEvent, analysis: dict[str, Any] | None) -> str:
    if analysis and str(analysis.get("severity", "")).lower() in ("low", "medium", "high"):
        sev = str(analysis.get("severity")).lower()
        if sev == "high":
            return "HIGH"
        if sev == "medium":
            return "MEDIUM"
        return "LOW"
    tags = [t.lower() for t in event.tags]
    for t in tags:
        if "disease" in t or "spot" in t or "fungal" in t or "wilt" in t:
            return "HIGH"
        if "healthy" in t or "ok" in t or "normal" in t:
            return "LOW"
    return "MEDIUM"


def _moisture_hint(event: NormalizedMediaEvent, analysis: dict[str, Any] | None) -> str:
    if analysis and analysis.get("irrigation_adjustment") == "increase":
        return "low (visual stress)"
    if analysis and analysis.get("irrigation_adjustment") == "decrease":
        return "sufficient / watch runoff"
    ctx = event.context if isinstance(event.context, dict) else {}
    if ctx and "moisture" in ctx:
        return str(ctx.get("moisture", "—"))
    return "n/a"


def _run_video_agent_chain(
    service: TwelveLabsClientService, video_id: str, event: NormalizedMediaEvent
) -> dict[str, Any]:
    """Mirror /api/analyze-video behavior for Cloudinary-driven videos."""
    last_err: str | None = None
    summary = None
    for _ in range(int(os.getenv("CLOUDINARY_12L_SUMMARY_RETRIES", "8"))):
        summary = service.summarize_video(
            video_id=video_id,
            summary_type="summary",
            prompt=STRUCTURED_CROP_SUMMARY_PROMPT,
        )
        if summary.status == "ready" and summary.text:
            break
        last_err = summary.error
        time.sleep(float(os.getenv("CLOUDINARY_12L_SUMMARY_WAIT_SEC", "2.0")))
    if not summary or summary.status != "ready" or not summary.text:
        return {
            "ok": False,
            "error": last_err or (summary.error if summary else "summary_failed"),
            "raw": None,
        }
    try:
        ai_data = json.loads(summary.text)
    except Exception:
        return {"ok": False, "error": "invalid_json_from_model", "raw": summary.text}

    adjustment = str(ai_data.get("irrigation_adjustment", "no_change") or "no_change")
    if adjustment == "decrease":
        irrigation = {"plan": "Reduce watering by 20%"}
    elif adjustment == "increase":
        irrigation = {"plan": "Increase watering by 15%"}
    else:
        irrigation = {"plan": "No change needed"}

    sustainability: dict[str, Any] = {
        "water_saved_liters": 120 if adjustment == "decrease" else 0,
        "fertilizer_reduction_percent": 15 if str(ai_data.get("disease", "none")).lower() not in ("none", "", "null") else 0,
        "story_beat": "Visual evidence can reduce over-irrigation and catch disease earlier — lowering water and chemical use.",
    }

    health = {
        "disease": ai_data.get("disease"),
        "severity": ai_data.get("severity"),
        "confidence": ai_data.get("confidence"),
    }

    risk_labels: list[str] = []
    sev = str(ai_data.get("severity", "")).lower()
    if sev:
        risk_labels.append(f"severity:{sev}")
    dis = str(ai_data.get("disease", ""))
    if dis and dis.lower() != "none":
        risk_labels.append(f"disease:{dis}")

    obs = ai_data.get("key_observations")
    if isinstance(obs, list):
        for o in obs[:3]:
            risk_labels.append(f"obs:{o}")

    return {
        "ok": True,
        "ai_data": ai_data,
        "health": health,
        "irrigation": irrigation,
        "sustainability": sustainability,
        "risk_labels": risk_labels,
    }


def process_cloudinary_webhook(
    raw_body: bytes,
    content_type: str | None,
    x_cld_timestamp: str | None,
    x_cld_signature: str | None,
) -> CloudinaryAnalysisOutput:
    """Verify signature, parse payload, run TwelveLabs + sustainability chain for video, or light path for image."""
    if not verify_notification_signature(raw_body, x_cld_timestamp, x_cld_signature):
        return CloudinaryAnalysisOutput(
            status="rejected",
            public_id="",
            resource_type="unknown",
            analysis_summary="Invalid or missing Cloudinary notification signature; set CLOUDINARY_API_SECRET and disable CLOUDINARY_WEBHOOK_SKIP_VERIFY in production.",
            risk_labels=[],
            recommended_action="",
            transformed_media_urls=TransformedMediaUrls(),
            error="invalid_webhook_signature",
        )

    try:
        flat: dict[str, Any] = parse_notification_body(raw_body, content_type)
    except (json.JSONDecodeError, ValueError) as exc:
        return CloudinaryAnalysisOutput(
            status="failed",
            public_id="",
            resource_type="unknown",
            analysis_summary="Could not parse Cloudinary notification body",
            risk_labels=[],
            recommended_action="",
            transformed_media_urls=TransformedMediaUrls(),
            error=f"parse_error:{exc}",
        )

    event = normalize_to_media_event(flat)
    return _analyze_normalized_event(event)


def process_cloudinary_local_event(payload: dict[str, Any]) -> CloudinaryAnalysisOutput:
    """
    Local-demo helper: analyze a Cloudinary upload result directly from frontend
    without requiring a webhook callback.
    """
    event = normalize_to_media_event(payload)
    return _analyze_normalized_event(event)


def _analyze_normalized_event(event: NormalizedMediaEvent) -> CloudinaryAnalysisOutput:
    if not event.public_id:
        return CloudinaryAnalysisOutput(
            status="failed",
            public_id="",
            resource_type=event.resource_type,
            analysis_summary="Missing public_id in notification",
            risk_labels=[],
            recommended_action="",
            transformed_media_urls=TransformedMediaUrls(),
            error="missing_public_id",
        )

    # Initial overlay labels; refined after 12L analysis
    base_risk = _risk_from_event(event, None)
    base_moist = _moisture_hint(event, None)
    base_labels = _compact_overlay_labels(_image_risk_labels(event, base_risk))
    derived_cloud = extract_cloud_name_from_url(event.secure_url)
    turls = build_transformation_urls(
        event.public_id,
        event.resource_type,
        event.version,
        base_risk,
        base_moist,
        overlay_labels=base_labels,
        cloud_name=derived_cloud,
    )
    if event.secure_url:
        turls.original_secure_url = event.secure_url

    is_video = event.resource_type == "video"
    if not is_video and event.secure_url and (
        "video" in event.secure_url.split("?")[0].lower() or "video/delivery" in (event.secure_url or "")
    ):
        is_video = True

    if not is_video:
        sustainability = _estimate_sustainability_metrics(event, is_video=False, risk_level=base_risk)
        image_labels = _image_risk_labels(event, base_risk)
        image_overlay_labels = f"{_compact_overlay_labels(image_labels)} {_overlay_metrics_badge(sustainability)}".strip()
        turls_img = build_transformation_urls(
            event.public_id,
            event.resource_type,
            event.version,
            base_risk,
            base_moist,
            overlay_labels=image_overlay_labels,
            cloud_name=derived_cloud,
        )
        if event.secure_url:
            turls_img.original_secure_url = event.secure_url
        rec = (
            "Continue image-based remote checks, track weekly trend tags, and prioritize interventions "
            "where risk is highest to reduce water, travel, and input waste."
        )
        return CloudinaryAnalysisOutput(
            status="success",
            public_id=event.public_id,
            resource_type=event.resource_type,
            analysis_summary=(
                "Image processed through Cloudinary delivery transforms. "
                "This supports low-friction farm-tech monitoring and environmental efficiency tracking."
            ),
            risk_labels=image_labels,
            recommended_action=rec,
            transformed_media_urls=turls_img,
            sustainability=sustainability,
        )

    video_url = event.secure_url or turls.original_secure_url
    if not video_url:
        return CloudinaryAnalysisOutput(
            status="failed",
            public_id=event.public_id,
            resource_type="video",
            analysis_summary="Video notification missing secure_url",
            risk_labels=[],
            recommended_action="Ensure uploads request secure_url in notification or use signed delivery URLs",
            transformed_media_urls=turls,
            error="missing_video_url",
        )

    service = TwelveLabsClientService()
    if not service.enabled or not service.api_key:
        or_msg = "TwelveLabs disabled: configure TWELVELABS_ENABLED and keys to enable video intelligence."
        return CloudinaryAnalysisOutput(
            status="success",
            public_id=event.public_id,
            resource_type="video",
            analysis_summary=or_msg,
            risk_labels=[f"tag:{t}" for t in event.tags],
            recommended_action="Enable TwelveLabs in .env, then re-upload the clip.",
            transformed_media_urls=turls,
            twelvelabs_error="twelvelabs_disabled" if not service.enabled else "missing_api_key",
            sustainability={"note": "Cloudinary is still your media system of record; AI analysis toggles on with TwelveLabs."},
        )

    ingest = service.ingest_video_url(video_url)
    video_id: str | None = ingest.video_id
    if ingest.status != "ready" or not video_id:
        return CloudinaryAnalysisOutput(
            status="partial",
            public_id=event.public_id,
            resource_type="video",
            analysis_summary=ingest.summary
            or "TwelveLabs indexing in progress. Retry analysis later or poll video_id in Agentverse tool.",
            risk_labels=[f"ingestion:{ingest.status}"],
            recommended_action="Re-run twelvelabs.ask_video or re-ingest from ASI:One with the returned video_id when ready.",
            transformed_media_urls=turls,
            video_id=ingest.video_id,
            index_id=ingest.index_id,
            stream_url=ingest.stream_url,
            twelvelabs_error=ingest.error,
        )

    chain = _run_video_agent_chain(service, video_id, event)
    if not chain.get("ok"):
        err = str(chain.get("error", "analysis_failed"))
        turls2 = build_transformation_urls(
            event.public_id,
            event.resource_type,
            event.version,
            "HIGH" if "invalid" in err else base_risk,
            base_moist,
            overlay_labels=base_labels,
            cloud_name=derived_cloud,
        )
        if event.secure_url:
            turls2.original_secure_url = event.secure_url
        return CloudinaryAnalysisOutput(
            status="partial",
            public_id=event.public_id,
            resource_type="video",
            analysis_summary=chain.get("raw")
            and str(chain.get("raw"))[:500]
            or f"Video indexed (video_id={video_id}) but structured analysis failed: {err}",
            risk_labels=[],
            recommended_action="Check TwelveLabs model output; optional: use twelvelabs.summarize_video for raw text",
            transformed_media_urls=turls2,
            video_id=video_id,
            index_id=ingest.index_id,
            stream_url=ingest.stream_url,
            twelvelabs_error=err,
        )

    ai_data = chain["ai_data"]
    turls3 = build_transformation_urls(
        event.public_id,
        event.resource_type,
        event.version,
        _risk_from_event(event, ai_data),
        _moisture_hint(event, ai_data),
        overlay_labels=(
            f"{_compact_overlay_labels(list(chain.get('risk_labels', [])))} "
            f"{_overlay_metrics_badge(sustainability)}"
        ).strip(),
        cloud_name=derived_cloud,
    )
    if event.secure_url:
        turls3.original_secure_url = event.secure_url

    actions = ai_data.get("recommended_actions", [])
    first_action = str(actions[0]) if isinstance(actions, list) and actions else str(ai_data.get("irrigation_adjustment", ""))
    if not first_action:
        first_action = chain["irrigation"].get("plan", "Monitor crop and soil moisture over the next 24–48h")

    sustainability = dict(chain["sustainability"])
    sustainability.update(_estimate_sustainability_metrics(event, is_video=True, risk_level=_risk_from_event(event, ai_data)))

    return CloudinaryAnalysisOutput(
        status="success",
        public_id=event.public_id,
        resource_type="video",
        analysis_summary=first_action
        or "Analysis complete. Review disease severity and irrigation plan below.",
        risk_labels=list(chain.get("risk_labels", []))[:20],
        recommended_action=str(chain["irrigation"].get("plan", "Adjust irrigation as indicated")),
        transformed_media_urls=turls3,
        video_id=video_id,
        index_id=ingest.index_id,
        stream_url=ingest.stream_url,
        twelvelabs_error=None,
        sustainability=sustainability,
        analysis=ai_data,  # type: ignore[assignment]
        health=chain["health"],  # type: ignore[assignment]
        irrigation=chain["irrigation"],  # type: ignore[assignment]
    )
