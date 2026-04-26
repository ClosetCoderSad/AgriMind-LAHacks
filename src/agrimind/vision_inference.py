from __future__ import annotations

import os
import json
from io import BytesIO
from pathlib import Path

import requests
import torch
from PIL import Image
from transformers import AutoProcessor, PaliGemmaForConditionalGeneration

from agrimind.schemas import Severity, VLMOutput

_MODEL = None
_PROCESSOR = None
_MODEL_DIR = None
_LABELS: list[str] | None = None


def _resolve_model_dir() -> str:
    return os.getenv("VLM_MODEL_DIR", "artifacts/paligemma-lora-fast")


def _resolve_label_source() -> str:
    return os.getenv("VLM_LABEL_SOURCE", "data/processed/train.jsonl")


def _load_labels() -> list[str]:
    global _LABELS
    if _LABELS is not None:
        return _LABELS

    source = Path(_resolve_label_source())
    labels: set[str] = set()
    if source.exists() and source.suffix == ".jsonl":
        with source.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                label = str(row.get("label", "")).strip()
                if label:
                    labels.add(label.lower())
    elif source.exists() and source.suffix == ".txt":
        for line in source.read_text(encoding="utf-8").splitlines():
            label = line.strip()
            if label:
                labels.add(label.lower())

    _LABELS = sorted(labels)
    return _LABELS


def _normalize_crop_hint(crop_hint: str | None) -> str:
    if not crop_hint:
        return ""
    hint = crop_hint.strip().lower().replace(" ", "_")
    return hint


def _filter_labels_by_crop(labels: list[str], crop_hint: str | None) -> list[str]:
    hint = _normalize_crop_hint(crop_hint)
    if not hint:
        return labels
    filtered = [label for label in labels if label.startswith(f"{hint}___") or hint in label]
    return filtered if filtered else labels


def _load_model() -> tuple[AutoProcessor, PaliGemmaForConditionalGeneration]:
    global _MODEL, _PROCESSOR, _MODEL_DIR
    model_dir = _resolve_model_dir()
    if _MODEL is not None and _PROCESSOR is not None and _MODEL_DIR == model_dir:
        return _PROCESSOR, _MODEL

    _PROCESSOR = AutoProcessor.from_pretrained(model_dir)
    _MODEL = PaliGemmaForConditionalGeneration.from_pretrained(model_dir, device_map="auto")
    _MODEL.eval()
    _MODEL_DIR = model_dir
    return _PROCESSOR, _MODEL


def preload_vlm() -> None:
    """Warm model + labels into memory to avoid first-request latency."""
    _load_model()
    _load_labels()


def _load_image(image_uri: str) -> Image.Image:
    if image_uri.startswith("http://") or image_uri.startswith("https://"):
        response = requests.get(image_uri, timeout=30)
        response.raise_for_status()
        return Image.open(BytesIO(response.content)).convert("RGB")

    path = Path(image_uri)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_uri}")
    return Image.open(path).convert("RGB")


def _normalize_prediction(text: str) -> str:
    cleaned = text.strip().lower()
    # Remove the prompt echo if the model returns it.
    cleaned = cleaned.replace("<image>", "").replace("identify crop health state.", "").strip()
    return cleaned.split("\n")[0][:120] if cleaned else "unknown_crop_condition"


def _severity_from_prediction(label: str) -> Severity:
    if "healthy" in label:
        return Severity.low
    if any(token in label for token in ("deficiency", "mosaic", "spot")):
        return Severity.medium
    if any(token in label for token in ("blight", "mildew", "rust", "rot")):
        return Severity.high
    return Severity.medium


def _confidence_from_prediction(label: str) -> float:
    if label == "unknown_crop_condition":
        return 0.45
    if "healthy" in label:
        return 0.9
    return 0.78


def _rank_labels_with_loss(
    image: Image.Image,
    processor: AutoProcessor,
    model: PaliGemmaForConditionalGeneration,
    crop_hint: str | None = None,
) -> tuple[str, float, list[dict[str, float]]]:
    labels = _filter_labels_by_crop(_load_labels(), crop_hint)
    if not labels:
        return "unknown_crop_condition", 0.45, [{"unknown_crop_condition": 0.45}]

    max_labels = int(os.getenv("VLM_MAX_LABELS", "0"))
    if max_labels > 0:
        labels = labels[:max_labels]

    prompt = "<image> Identify crop health state."
    neg_losses: list[float] = []
    with torch.no_grad():
        for label in labels:
            model_inputs = processor(
                text=prompt,
                images=image,
                suffix=label,
                return_tensors="pt",
            ).to(model.device)
            out = model(**model_inputs)
            neg_losses.append(-float(out.loss.item()))

    probs = torch.softmax(torch.tensor(neg_losses, dtype=torch.float32), dim=0).tolist()
    ranked = sorted(zip(labels, probs), key=lambda x: x[1], reverse=True)
    top_k_count = int(os.getenv("VLM_TOP_K", "3"))
    top_k = [{label: round(score, 4)} for label, score in ranked[:top_k_count]]

    best_label, best_score = ranked[0]
    return best_label, float(best_score), top_k


def run_vlm_inference(image_uri: str, crop_hint: str | None = None) -> VLMOutput:
    """Run local VLM inference from fine-tuned checkpoint with real top-k."""
    processor, model = _load_model()
    image = _load_image(image_uri)
    inference_mode = os.getenv("VLM_INFERENCE_MODE", "label_ranking")

    if inference_mode == "generate":
        prompt = "<image> Identify crop health state."
        inputs = processor(text=prompt, images=image, return_tensors="pt").to(model.device)
        with torch.no_grad():
            output = model.generate(**inputs, max_new_tokens=24, do_sample=False)
        decoded = processor.batch_decode(output, skip_special_tokens=True)[0]
        label = _normalize_prediction(decoded)
        confidence = _confidence_from_prediction(label)
        top_k = [{label: round(confidence, 4)}]
    else:
        label, confidence, top_k = _rank_labels_with_loss(
            image=image,
            processor=processor,
            model=model,
            crop_hint=crop_hint,
        )

    low_conf_threshold = float(os.getenv("VLM_LOW_CONFIDENCE_THRESHOLD", "0.4"))
    if confidence < low_conf_threshold:
        label = "uncertain_crop_condition"
        severity = Severity.low
        evidence = [
            f"low_confidence_prediction={top_k[0] if top_k else 'none'}",
            "recommend_rescan=true",
        ]
        return VLMOutput(
            disease_or_stress_label=label,
            severity=severity,
            confidence=confidence,
            visual_evidence=evidence,
            top_k=top_k,
        )

    severity = _severity_from_prediction(label)
    evidence = [f"model_prediction={label}"]

    return VLMOutput(
        disease_or_stress_label=label,
        severity=severity,
        confidence=confidence,
        visual_evidence=evidence,
        top_k=top_k,
    )
