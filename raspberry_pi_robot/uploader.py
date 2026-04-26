from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import requests

import config


class SupercomputerUploader:
    def __init__(self) -> None:
        self.enabled = config.UPLOAD_ENABLED
        self.url = config.SUPERCOMPUTER_ANALYZE_UPLOAD_URL
        self.timeout = config.UPLOAD_TIMEOUT_SECONDS

    def send_capture(self, image_path: str, sensor_values: dict) -> dict:
        if not self.enabled:
            return {"status": "disabled", "message": "Upload is disabled in config.py"}

        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found for upload: {image_path}")

        scan_id = f"scan-{uuid4().hex[:10]}"
        form_data = {
            "scan_id": scan_id,
            "gps_or_row_id": config.GPS_OR_ROW_ID,
            "moisture_pct": str(sensor_values["moisture_pct"]),
            "air_quality_index": str(sensor_values["air_quality_index"]),
            "light_lux": str(sensor_values["light_lux_est"]),
            "temperature_c": str(sensor_values["temperature_c"]),
            "crop_type": config.CROP_TYPE,
            "device_id": config.DEVICE_ID,
        }

        with path.open("rb") as f:
            files = {"image": (path.name, f, "image/jpeg")}
            response = requests.post(
                self.url,
                data=form_data,
                files=files,
                timeout=self.timeout,
            )
        response.raise_for_status()
        return response.json()
