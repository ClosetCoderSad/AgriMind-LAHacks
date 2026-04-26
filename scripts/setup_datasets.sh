#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[1/8] Creating dataset directories..."
mkdir -p data/raw data/raw/plantvillage data/raw/plantdoc data/raw/plantvillage_src

if [[ ! -f .venv/bin/python ]]; then
  echo "Virtualenv missing at .venv. Create it first: python3 -m venv .venv"
  exit 1
fi

echo "[2/8] Ensuring Kaggle CLI is available in venv..."
.venv/bin/pip install kaggle

if [[ -n "${KAGGLE_API_TOKEN:-}" ]]; then
  echo "Using Kaggle auth from KAGGLE_API_TOKEN environment variable."
elif [[ -f "$HOME/.kaggle/kaggle.json" ]]; then
  chmod 600 "$HOME/.kaggle/kaggle.json"
  echo "Using Kaggle auth from ~/.kaggle/kaggle.json."
else
  echo "Missing Kaggle credentials."
  echo "Provide one of the following before running this script:"
  echo "  1) export KAGGLE_API_TOKEN='<your_token>'"
  echo "  2) ~/.kaggle/kaggle.json (legacy method)"
  exit 1
fi

echo "[3/8] Downloading PlantVillage from Kaggle..."
.venv/bin/kaggle datasets download -d vipoooool/new-plant-diseases-dataset -p data/raw

echo "[4/8] Extracting PlantVillage archive..."
unzip -o data/raw/new-plant-diseases-dataset.zip -d data/raw/plantvillage_src

echo "[5/8] Reorganizing PlantVillage class folders..."
.venv/bin/python - <<'PY'
from pathlib import Path
import shutil

src_root = Path("data/raw/plantvillage_src")
dst_root = Path("data/raw/plantvillage")
train_dirs = [p for p in src_root.rglob("train") if p.is_dir()]
if not train_dirs:
    raise SystemExit("Could not find PlantVillage train directory under data/raw/plantvillage_src")
train_dir = train_dirs[0]
for class_dir in sorted(train_dir.iterdir()):
    if class_dir.is_dir():
        target = dst_root / class_dir.name
        target.mkdir(parents=True, exist_ok=True)
        for img in class_dir.rglob("*"):
            if img.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                shutil.copy2(img, target / img.name)

valid_dirs = [p for p in src_root.rglob("valid") if p.is_dir()]
if valid_dirs:
    valid_dir = valid_dirs[0]
    for class_dir in sorted(valid_dir.iterdir()):
        if class_dir.is_dir():
            target = dst_root / class_dir.name
            target.mkdir(parents=True, exist_ok=True)
            for img in class_dir.rglob("*"):
                if img.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                    shutil.copy2(img, target / img.name)
print("PlantVillage reorganization complete.")
PY

echo "[6/8] Downloading PlantDoc from GitHub..."
rm -rf data/raw/plantdoc_src
git clone https://github.com/pratikkayal/PlantDoc-Dataset.git data/raw/plantdoc_src

echo "[7/8] Reorganizing PlantDoc class folders..."
.venv/bin/python - <<'PY'
from pathlib import Path
import shutil

src_root = Path("data/raw/plantdoc_src")
dst_root = Path("data/raw/plantdoc")
count = 0
for img in src_root.rglob("*"):
    if img.is_file() and img.suffix.lower() in {".jpg", ".jpeg", ".png"}:
        class_name = img.parent.name.strip().replace(" ", "_")
        target_dir = dst_root / class_name
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(img, target_dir / img.name)
        count += 1
print(f"Copied {count} PlantDoc images.")
PY

echo "[8/8] Building train/val/test splits..."
.venv/bin/python scripts/prepare_datasets.py --out data/processed

echo "Done. Output files:"
ls -lh data/processed
