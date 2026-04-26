#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image
from transformers import AutoProcessor, PaliGemmaForConditionalGeneration


def _read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate PaliGemma baseline on test set.")
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--test-json", type=Path, required=True)
    parser.add_argument("--max-samples", type=int, default=200)
    args = parser.parse_args()

    processor = AutoProcessor.from_pretrained(args.model_dir)
    model = PaliGemmaForConditionalGeneration.from_pretrained(args.model_dir, device_map="auto")

    rows = _read_jsonl(args.test_json)[: args.max_samples]
    correct = 0
    total = len(rows)

    for row in rows:
        image = Image.open(row["image_path"]).convert("RGB")
        inputs = processor(text="<image> Identify crop health state.", images=image, return_tensors="pt").to(
            model.device
        )
        output = model.generate(**inputs, max_new_tokens=16, do_sample=False)
        pred = processor.batch_decode(output, skip_special_tokens=True)[0].lower()
        if row["label"].lower() in pred:
            correct += 1

    acc = correct / total if total else 0.0
    print(json.dumps({"samples": total, "top1_string_match_acc": acc}, indent=2))


if __name__ == "__main__":
    main()
