#!/usr/bin/env python3
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agrimind.edge_queue import CaptureQueue
from agrimind.schemas import CaptureEvent, SensorValues


def main() -> None:
    queue = CaptureQueue()
    queue.clear()

    for i in range(5):
        event = CaptureEvent(
            scan_id=f"offline-{i}",
            timestamp=datetime.now(timezone.utc),
            gps_or_row_id=f"row-{i}",
            image_uri=f"https://example.com/{i}.jpg",
            sensor_values=SensorValues(
                moisture_pct=35,
                air_quality_index=80,
                light_lux=12000,
                temperature_c=30,
            ),
        )
        queue.enqueue(event)

    replay = queue.load_all()
    print(f"queued={len(replay)}")
    queue.clear()
    print("queue_cleared=true")


if __name__ == "__main__":
    main()
