#!/usr/bin/env python3
from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path


def _pick_images(class_dir: Path, per_class: int, rng: random.Random) -> list[Path]:
    images = [
        p
        for p in class_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    ]
    if not images:
        return []
    rng.shuffle(images)
    return images[: min(per_class, len(images))]


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare camera demo samples for phone display.")
    parser.add_argument("--src", default="data/raw/plantvillage", help="Dataset root directory")
    parser.add_argument("--out", default="demo_assets/iphone_samples", help="Output directory")
    parser.add_argument("--classes", type=int, default=8, help="Number of classes to include")
    parser.add_argument("--per-class", type=int, default=3, help="Images per class")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    src = Path(args.src)
    out = Path(args.out)
    if not src.exists():
        raise SystemExit(f"Source dataset directory not found: {src}")

    rng = random.Random(args.seed)
    class_dirs = sorted([p for p in src.iterdir() if p.is_dir()])
    if not class_dirs:
        raise SystemExit(f"No class folders found under: {src}")
    rng.shuffle(class_dirs)
    picked_classes = class_dirs[: min(args.classes, len(class_dirs))]

    out.mkdir(parents=True, exist_ok=True)
    copied = 0
    for class_dir in picked_classes:
        target_class_dir = out / class_dir.name
        target_class_dir.mkdir(parents=True, exist_ok=True)
        for img_path in _pick_images(class_dir, args.per_class, rng):
            dst = target_class_dir / img_path.name
            shutil.copy2(img_path, dst)
            copied += 1

    info_file = out / "README.txt"
    info_file.write_text(
        "IPhone camera demo samples generated from local dataset.\n"
        "Open these images fullscreen on your phone and point robot camera at the screen.\n"
        "Use one class at a time for clearer inference.\n",
        encoding="utf-8",
    )
    print(f"Prepared {copied} images in: {out}")


if __name__ == "__main__":
    main()
