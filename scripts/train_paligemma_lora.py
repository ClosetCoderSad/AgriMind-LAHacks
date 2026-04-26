#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from datasets import Dataset
from peft import LoraConfig, get_peft_model
from PIL import Image
from transformers import AutoProcessor, PaliGemmaForConditionalGeneration, Trainer, TrainingArguments


def _read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _to_dataset(rows: list[dict]) -> Dataset:
    return Dataset.from_list(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune PaliGemma with LoRA on crop datasets.")
    parser.add_argument("--model-id", default="google/paligemma-3b-pt-224")
    parser.add_argument("--train-json", type=Path, required=True)
    parser.add_argument("--val-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/paligemma-lora"))
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--num-workers", type=int, default=4)
    args = parser.parse_args()

    processor = AutoProcessor.from_pretrained(args.model_id)
    model = PaliGemmaForConditionalGeneration.from_pretrained(args.model_id)

    lora_cfg = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_cfg)

    train_ds = _to_dataset(_read_jsonl(args.train_json))
    val_ds = _to_dataset(_read_jsonl(args.val_json))

    def preprocess(example: dict) -> dict:
        image = Image.open(example["image_path"]).convert("RGB")
        prompt = "<image> Identify crop health state."
        target = example["label"]
        model_inputs = processor(text=prompt, images=image, suffix=target, return_tensors="pt")
        return {k: v.squeeze(0) for k, v in model_inputs.items()}

    train_ds = train_ds.map(preprocess, remove_columns=train_ds.column_names)
    val_ds = val_ds.map(preprocess, remove_columns=val_ds.column_names)

    train_args = TrainingArguments(
        output_dir=str(args.output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        logging_steps=50,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=2,
        learning_rate=2e-4,
        fp16=False,
        bf16=True,
        dataloader_num_workers=args.num_workers,
        dataloader_pin_memory=True,
        remove_unused_columns=False,
        report_to=[],
    )

    trainer = Trainer(
        model=model,
        args=train_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
    )
    trainer.train()
    trainer.save_model(str(args.output_dir))
    processor.save_pretrained(str(args.output_dir))
    print(f"Saved LoRA model to {args.output_dir}")


if __name__ == "__main__":
    main()
