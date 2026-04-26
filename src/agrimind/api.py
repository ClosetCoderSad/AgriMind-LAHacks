from __future__ import annotations

import json
import pickle
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi import File, Form, UploadFile

from agrimind.fusion import fuse_sensor_and_vision
from agrimind.gemma4_pipeline import Gemma4Advisor
from agrimind.schemas import CaptureEvent, SensorValues
from agrimind.vision_inference import preload_vlm, run_vlm_inference

app = FastAPI(title="AgriMind API", version="0.1.0")
advisor = Gemma4Advisor()
upload_dir = Path("data/uploads")
upload_dir.mkdir(parents=True, exist_ok=True)
result_pkl_dir = Path("data/results_pkl")
result_pkl_dir.mkdir(parents=True, exist_ok=True)
result_json_dir = Path("data/results_json")
result_json_dir.mkdir(parents=True, exist_ok=True)


def _persist_result_pickle(scan_id: str, result: dict) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = result_pkl_dir / f"{scan_id}_{ts}.pkl"
    with out_path.open("wb") as f:
        pickle.dump(result, f)
    return str(out_path.resolve())


def _persist_result_json(scan_id: str, result: dict) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = result_json_dir / f"{scan_id}_{ts}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return str(out_path.resolve())


@app.on_event("startup")
def startup_warmup() -> None:
    preload_vlm()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze")
def analyze(capture: CaptureEvent) -> dict:
    crop_hint = capture.metadata.get("crop_type", "")
    vlm_output = run_vlm_inference(str(capture.image_uri), crop_hint=crop_hint)
    fused = fuse_sensor_and_vision(capture, vlm_output)
    advice = advisor.advise(fused)
    result = {
        "capture": capture.model_dump(),
        "vlm_output": vlm_output.model_dump(),
        "fusion_output": fused.model_dump(),
        "gemma_advice": advice.model_dump(),
    }
    result["result_pkl_path"] = _persist_result_pickle(capture.scan_id, result)
    result["result_json_path"] = _persist_result_json(capture.scan_id, result)
    return result


@app.post("/analyze_upload")
async def analyze_upload(
    image: UploadFile = File(...),
    scan_id: str = Form(...),
    gps_or_row_id: str = Form(...),
    moisture_pct: float = Form(...),
    air_quality_index: float = Form(...),
    light_lux: float = Form(...),
    temperature_c: float = Form(...),
    crop_type: str = Form(""),
    device_id: str = Form("pi-robot"),
) -> dict:
    ts = datetime.now(timezone.utc)
    safe_name = image.filename or f"{scan_id}.jpg"
    save_path = upload_dir / f"{scan_id}_{safe_name}".replace(" ", "_")
    payload = await image.read()
    save_path.write_bytes(payload)

    capture = CaptureEvent(
        scan_id=scan_id,
        timestamp=ts,
        gps_or_row_id=gps_or_row_id,
        image_uri=str(save_path.resolve()),
        sensor_values=SensorValues(
            moisture_pct=moisture_pct,
            air_quality_index=air_quality_index,
            light_lux=light_lux,
            temperature_c=temperature_c,
        ),
        metadata={"device_id": device_id, "crop_type": crop_type},
    )
    return analyze(capture)
