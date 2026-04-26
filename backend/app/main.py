from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl

from backend.models.contracts import DecisionRequest, ExplainRequest, ExplainResponse
from backend.services.cloudinary_pipeline import process_cloudinary_local_event, process_cloudinary_webhook
from backend.services.pipeline import run_agri_pipeline
from backend.services.twelvelabs_client import TwelveLabsClientService
from backend.storage.local_store import LocalStore

load_dotenv()

cors_origin = os.getenv("CORS_ORIGIN", "http://localhost:5173")
db_path = os.getenv("SQLITE_PATH", "backend/storage/agrimind.db")
store = LocalStore(db_path)

app = FastAPI(title="AgriMind API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[cors_origin],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class IngestVideoRequest(BaseModel):
    video_url: HttpUrl
    source_key: str | None = None


class SummarizeVideoRequest(BaseModel):
    video_id: str
    summary_type: str = "summary"
    prompt: str | None = None


class VideoQuestionRequest(BaseModel):
    video_id: str
    question: str


class CloudinaryLocalAnalyzeRequest(BaseModel):
    public_id: str
    secure_url: str
    url: str | None = None
    width: int | None = None
    height: int | None = None
    format: str | None = None
    resource_type: str = "image"
    bytes: int | None = None
    created_at: str | None = None
    tags: list[str] = []
    version: int | str | None = None


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/cloudinary/webhook")
async def cloudinary_webhook(request: Request) -> dict:
    """
    Cloudinary upload/notification callback. Verifies X-Cld-Signature + X-Cld-Timestamp, runs
    media + TwelveLabs + sustainability flow, and persists the result.
    """
    body = await request.body()
    sig = request.headers.get("X-Cld-Signature") or request.headers.get("x-cld-signature")
    ts = request.headers.get("X-Cld-Timestamp") or request.headers.get("x-cld-timestamp")
    ct = request.headers.get("content-type") or request.headers.get("Content-Type")
    out = process_cloudinary_webhook(body, ct, ts, sig)
    data = out.model_dump(mode="json")
    if out.status == "rejected":
        raise HTTPException(status_code=403, detail=data)
    eid = store.save_cloudinary_event(data)
    data["event_id"] = eid
    return data


@app.get("/api/cloudinary/latest")
def cloudinary_latest() -> dict:
    row = store.latest_cloudinary_event()
    if not row:
        return {"status": "empty", "message": "No Cloudinary webhook events yet."}
    return {
        "status": "ok",
        "id": row["id"],
        "created_at": row["created_at"],
        "result": row["result"],
    }


@app.get("/api/cloudinary/events")
def cloudinary_events(limit: int = 20) -> list[dict]:
    return store.list_cloudinary_events(limit=limit)


@app.post("/api/cloudinary/local-analyze")
def cloudinary_local_analyze(request: CloudinaryLocalAnalyzeRequest) -> dict:
    """
    Local-demo endpoint to simulate webhook-triggered analysis from an uploaded
    Cloudinary asset payload directly.
    """
    out = process_cloudinary_local_event(request.model_dump(mode="json"))
    data = out.model_dump(mode="json")
    eid = store.save_cloudinary_event(data)
    data["event_id"] = eid
    return data


@app.get("/api/history")
def history(limit: int = 10) -> list[dict]:
    return store.latest(limit)


@app.get("/api/twelvelabs/history")
def twelvelabs_history(limit: int = 20) -> list[dict]:
    return store.latest_twelvelabs_ingestion(limit)


@app.get("/api/twelvelabs/videos")
def twelvelabs_videos(index_id: str | None = None, limit: int = 20) -> dict:
    videos, error = TwelveLabsClientService().list_index_videos(index_id=index_id, limit=limit)
    return {
        "videos": [
            {
                "video_id": video.video_id,
                "index_id": video.index_id,
                "filename": video.filename,
                "duration": video.duration,
                "created_at": video.created_at,
                "stream_url": video.stream_url,
            }
            for video in videos
        ],
        "error": error,
    }


@app.post("/api/twelvelabs/summarize")
def twelvelabs_summarize(request: SummarizeVideoRequest) -> dict:
    structured_prompt = """
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
    result = TwelveLabsClientService().summarize_video(
        video_id=request.video_id,
        summary_type=request.summary_type,
        prompt=structured_prompt,
    )
    return {
        "status": result.status,
        "text": result.text,
        "error": result.error,
    }


@app.post("/api/twelvelabs/qna")
def twelvelabs_qna(request: VideoQuestionRequest) -> dict:
    result = TwelveLabsClientService().ask_video(video_id=request.video_id, question=request.question)
    return {
        "status": result.status,
        "text": result.text,
        "error": result.error,
    }


@app.post("/api/health/ingest-video")
def ingest_video(request: IngestVideoRequest) -> dict:
    result = TwelveLabsClientService().ingest_video_url(str(request.video_url))
    store.save_twelvelabs_ingestion(
        {
            "source_key": request.source_key,
            "status": result.status,
            "index_id": result.index_id,
            "asset_id": result.asset_id,
            "indexed_asset_id": result.indexed_asset_id,
            "video_id": result.video_id,
            "stream_url": result.stream_url,
            "search_reference": result.search_reference,
            "error": result.error,
        }
    )
    return {
        "status": result.status,
        "summary": result.summary,
        "index_id": result.index_id,
        "asset_id": result.asset_id,
        "indexed_asset_id": result.indexed_asset_id,
        "video_id": result.video_id,
        "stream_url": result.stream_url,
        "search_reference": result.search_reference,
        "error": result.error,
    }


@app.post("/api/decision")
def decision(request: DecisionRequest):
    result = run_agri_pipeline(request, ingestion_store=store)
    store.save_decision(result.model_dump())
    return result


@app.post("/api/explain", response_model=ExplainResponse)
def explain(request: ExplainRequest) -> ExplainResponse:
    decision = request.decision

    if decision.action == "no_watering":
        action_text = "Watering is not needed right now"
    elif decision.action == "light_watering":
        action_text = "Use a short, light watering cycle"
    else:
        action_text = "Water now to avoid moisture stress"

    explanation = (
        f"Plant status shows {decision.disease.replace('_', ' ')}. "
        f"{action_text}. "
        f"This decision is estimated to save {decision.impact.water_saved_ml}ml of water "
        f"with {decision.impact.risk_level} operational risk."
    )

    return ExplainResponse(explanation=explanation)


import json

class AnalyzeVideoRequest(BaseModel):
    video_id: str


@app.post("/api/analyze-video")
def analyze_video(request: AnalyzeVideoRequest) -> dict:
    service = TwelveLabsClientService()

    # Step 1: Get structured AI output
    structured_prompt = """
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

    summary = service.summarize_video(
        video_id=request.video_id,
        summary_type="summary",
        prompt=structured_prompt,
    )

    if summary.status != "ready" or not summary.text:
        return {"status": "failed", "error": summary.error or "summary_failed"}

    try:
        ai_data = json.loads(summary.text)
    except Exception:
        return {"status": "failed", "error": "invalid_json_from_model", "raw": summary.text}

    # Step 2: Health Agent
    health = {
        "disease": ai_data.get("disease"),
        "severity": ai_data.get("severity"),
        "confidence": ai_data.get("confidence"),
    }

    # Step 3: Irrigation Agent
    adjustment = ai_data.get("irrigation_adjustment", "no_change")

    if adjustment == "decrease":
        irrigation = {"plan": "Reduce watering by 20%"}
    elif adjustment == "increase":
        irrigation = {"plan": "Increase watering by 15%"}
    else:
        irrigation = {"plan": "No change needed"}

    # Step 4: Sustainability Agent (simple calc for demo)
    sustainability = {
        "water_saved_liters": 120 if adjustment == "decrease" else 0,
        "fertilizer_reduction_percent": 15 if ai_data.get("disease") != "none" else 0,
    }

    return {
        "status": "success",
        "analysis": ai_data,
        "health": health,
        "irrigation": irrigation,
        "sustainability": sustainability,
    }
