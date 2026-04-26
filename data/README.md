# Dataset Placement

Place extracted datasets in:

- `data/raw/plantvillage/<class_name>/*.jpg`
- `data/raw/plantdoc/<class_name>/*.jpg`

One-shot automation (download + reorganization + split generation):

- `export KAGGLE_API_TOKEN='<your_token>'` (or use legacy `~/.kaggle/kaggle.json`)
- `bash scripts/setup_datasets.sh`

Then run:

- `python scripts/prepare_datasets.py --out data/processed`

This generates:

- `data/processed/train.jsonl`
- `data/processed/val.jsonl`
- `data/processed/test.jsonl`
- `data/processed/real_capture_holdout.jsonl`
