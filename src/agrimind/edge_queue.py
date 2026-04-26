from __future__ import annotations

import json
from pathlib import Path

from agrimind.schemas import CaptureEvent


class CaptureQueue:
    """Local disk queue for Pi upload retries."""

    def __init__(self, queue_file: str = "data/queue/pending.jsonl") -> None:
        self.queue_file = Path(queue_file)
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        self.queue_file.touch(exist_ok=True)

    def enqueue(self, event: CaptureEvent) -> None:
        with self.queue_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event.model_dump(mode="json")) + "\n")

    def load_all(self) -> list[dict]:
        with self.queue_file.open("r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def clear(self) -> None:
        self.queue_file.write_text("", encoding="utf-8")
