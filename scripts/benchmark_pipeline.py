#!/usr/bin/env python3
from __future__ import annotations

import argparse
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agrimind.fusion import fuse_sensor_and_vision
from agrimind.schemas import CaptureEvent, SensorValues
from agrimind.vision_inference import run_vlm_inference


def main() -> None:
    parser = argparse.ArgumentParser(description="Latency and reliability smoke checks.")
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--image-uri", default="https://example.com/crop.jpg")
    args = parser.parse_args()

    latencies_ms: list[float] = []
    errors = 0

    for i in range(args.iterations):
        capture = CaptureEvent(
            scan_id=f"bench-{i}",
            timestamp=datetime.now(timezone.utc),
            gps_or_row_id=f"row-{i%4}",
            image_uri=args.image_uri,
            sensor_values=SensorValues(
                moisture_pct=40 + (i % 8),
                air_quality_index=65 + i,
                light_lux=10000 + i * 40,
                temperature_c=27 + (i % 6),
            ),
        )
        start = time.perf_counter()
        try:
            vlm = run_vlm_inference(args.image_uri)
            _ = fuse_sensor_and_vision(capture, vlm)
        except Exception:
            errors += 1
            continue
        latencies_ms.append((time.perf_counter() - start) * 1000)

    if not latencies_ms:
        print("No successful runs.")
        return

    print(f"runs={len(latencies_ms)} errors={errors}")
    print(f"p50_ms={statistics.median(latencies_ms):.2f}")
    print(f"p95_ms={sorted(latencies_ms)[int(0.95 * (len(latencies_ms) - 1))]:.2f}")
    print(f"max_ms={max(latencies_ms):.2f}")


if __name__ == "__main__":
    main()
