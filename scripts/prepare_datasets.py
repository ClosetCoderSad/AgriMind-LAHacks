#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from random import Random


def _collect_labeled_images(root: Path) -> list[dict]:
    items: list[dict] = []
    for class_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        label = class_dir.name
        for img in class_dir.rglob("*"):
            if img.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                items.append({"image_path": str(img.resolve()), "label": label})
    return items


def _split(items: list[dict], seed: int, train_ratio: float, val_ratio: float):
    rng = Random(seed)
    rng.shuffle(items)
    n = len(items)
    n_train = int(n * train_ratio)
    n_val = int(n * val_ratio)
    train = items[:n_train]
    val = items[n_train : n_train + n_val]
    test = items[n_train + n_val :]
    return train, val, test


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare PlantVillage/PlantDoc splits.")
    parser.add_argument("--plantvillage", type=Path, default=Path("data/raw/plantvillage"))
    parser.add_argument("--plantdoc", type=Path, default=Path("data/raw/plantdoc"))
    parser.add_argument("--out", type=Path, default=Path("data/processed"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    args = parser.parse_args()

    merged: list[dict] = []
    if args.plantvillage.exists():
        merged.extend(_collect_labeled_images(args.plantvillage))
    if args.plantdoc.exists():
        merged.extend(_collect_labeled_images(args.plantdoc))

    if not merged:
        raise SystemExit(
            "No images found. Place datasets under data/raw/plantvillage and/or data/raw/plantdoc."
        )

    train, val, test = _split(merged, args.seed, args.train_ratio, args.val_ratio)

    _write_jsonl(args.out / "train.jsonl", train)
    _write_jsonl(args.out / "val.jsonl", val)
    _write_jsonl(args.out / "test.jsonl", test)
    _write_jsonl(args.out / "real_capture_holdout.jsonl", [])

    print(
        json.dumps(
            {
                "total": len(merged),
                "train": len(train),
                "val": len(val),
                "test": len(test),
                "holdout_note": "Fill real_capture_holdout.jsonl with Logitech camera captures.",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
