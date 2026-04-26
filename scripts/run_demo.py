#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agrimind.fusion import fuse_sensor_and_vision
from agrimind.gemma4_pipeline import Gemma4Advisor
from agrimind.schemas import CaptureEvent, SensorValues
from agrimind.vision_inference import run_vlm_inference


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an end-to-end local demo.")
    parser.add_argument("--input-image", required=True, help="Local image path or URL string")
    parser.add_argument("--scan-id", default="scan-demo-001")
    parser.add_argument("--gps-or-row-id", default="row-7")
    args = parser.parse_args()

    capture = CaptureEvent(
        scan_id=args.scan_id,
        timestamp=datetime.now(timezone.utc),
        gps_or_row_id=args.gps_or_row_id,
        image_uri=args.input_image,
        sensor_values=SensorValues(
            moisture_pct=29.5,
            air_quality_index=88,
            light_lux=12400,
            temperature_c=31.2,
        ),
    )

    vlm = run_vlm_inference(args.input_image)
    fused = fuse_sensor_and_vision(capture, vlm)
    advice = Gemma4Advisor().advise(fused)

    print(
        json.dumps(
            {
                "capture": capture.model_dump(mode="json"),
                "vlm_output": vlm.model_dump(),
                "fusion_output": fused.model_dump(),
                "gemma_advice": advice.model_dump(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
