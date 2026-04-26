"""
Standalone leaf disease image classifier + optional local API server.

This script keeps your existing backend untouched and runs independently from:
    classification-model/leaf_disease_classifier.py
"""

import argparse
import io
import json
import urllib.request
from pathlib import Path
from typing import Any, List

import torch
from PIL import Image
from torchvision import models, transforms

MODEL_URL = (
    "https://huggingface.co/huyhuy07/leaf-disease-detector-models/resolve/main/"
    "mobilenetv2_leaf_offline_15ep.pth"
)
MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_PATH = MODEL_DIR / "mobilenetv2_leaf_offline_15ep.pth"

# Fallback class labels if you do not provide --labels-json.
# If your model was trained with a different label order, pass your own JSON list.
DEFAULT_LABELS: List[str] = [
    "Pepper__bell___Bacterial_spot",
    "Pepper__bell___healthy",
    "Potato___Early_blight",
    "Potato___Late_blight",
    "Potato___healthy",
    "Tomato_Bacterial_spot",
    "Tomato_Early_blight",
    "Tomato_Late_blight",
    "Tomato_Leaf_Mold",
    "Tomato_Septoria_leaf_spot",
    "Tomato_Spider_mites",
    "Tomato_Target_Spot",
    "Tomato_Tomato_mosaic_virus",
    "Tomato_Tomato_YellowLeaf_Curl_Virus",
    "Tomato_healthy",
]
BINARY_DEFAULT_LABELS: List[str] = ["healthy", "diseased"]


def ensure_model_downloaded() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    if MODEL_PATH.exists():
        return
    print(f"Downloading model from:\n{MODEL_URL}\n")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    print(f"Saved model to: {MODEL_PATH}")


def build_model(weights_path: Path) -> torch.nn.Module:
    state = torch.load(weights_path, map_location="cpu")
    if isinstance(state, dict) and "state_dict" in state:
        state = state["state_dict"]

    # Infer class count from final classifier layer in state dict.
    out_features = None
    if isinstance(state, dict):
        key = "classifier.1.weight"
        if key in state and hasattr(state[key], "shape"):
            out_features = int(state[key].shape[0])
    if out_features is None:
        raise RuntimeError("Could not infer output classes from model state dict.")

    model = models.mobilenet_v2(weights=None)
    model.classifier[1] = torch.nn.Linear(model.last_channel, out_features)
    model.load_state_dict(state, strict=True)
    model.eval()
    return model


def load_labels(labels_json: str | None, num_classes: int) -> List[str]:
    if labels_json:
        labels_path = Path(labels_json)
        data = json.loads(labels_path.read_text(encoding="utf-8"))
        if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
            raise ValueError("labels json must be a JSON array of strings.")
        if len(data) != num_classes:
            raise ValueError(f"labels count ({len(data)}) does not match model outputs ({num_classes}).")
        return data

    if len(DEFAULT_LABELS) == num_classes:
        return DEFAULT_LABELS
    if num_classes == 2:
        return BINARY_DEFAULT_LABELS
    return [f"class_{i}" for i in range(num_classes)]


def preprocess_image(image_path: Path) -> torch.Tensor:
    transform = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ]
    )
    img = Image.open(image_path).convert("RGB")
    return transform(img).unsqueeze(0)


@torch.no_grad()
def predict_topk(image_path: Path, labels_json: str | None, top_k: int) -> List[dict[str, Any]]:
    ensure_model_downloaded()
    model = build_model(MODEL_PATH)
    labels = load_labels(labels_json, num_classes=model.classifier[1].out_features)
    tensor = preprocess_image(image_path)

    logits = model(tensor)
    probs = torch.softmax(logits, dim=1)[0]
    top_probs, top_indices = torch.topk(probs, k=min(top_k, len(labels)))

    predictions: List[dict[str, Any]] = []
    for rank, (idx, prob) in enumerate(zip(top_indices.tolist(), top_probs.tolist()), start=1):
        predictions.append(
            {
                "rank": rank,
                "label": labels[idx],
                "confidence": float(prob),
            }
        )
    return predictions


@torch.no_grad()
def predict(image_path: Path, labels_json: str | None, top_k: int) -> None:
    predictions = predict_topk(image_path=image_path, labels_json=labels_json, top_k=top_k)

    print(f"\nImage: {image_path}")
    print("Top predictions:")
    for item in predictions:
        print(f"{item['rank']}. {item['label']} ({item['confidence'] * 100:.2f}%)")


def predict_from_bytes(image_bytes: bytes, labels_json: str | None, top_k: int) -> List[dict[str, Any]]:
    ensure_model_downloaded()
    model = build_model(MODEL_PATH)
    labels = load_labels(labels_json, num_classes=model.classifier[1].out_features)
    transform = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ]
    )
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    tensor = transform(img).unsqueeze(0)
    logits = model(tensor)
    probs = torch.softmax(logits, dim=1)[0]
    top_probs, top_indices = torch.topk(probs, k=min(top_k, len(labels)))
    return [
        {
            "rank": rank,
            "label": labels[idx],
            "confidence": float(prob),
        }
        for rank, (idx, prob) in enumerate(zip(top_indices.tolist(), top_probs.tolist()), start=1)
    ]


def run_server(host: str, port: int, labels_json: str | None) -> None:
    try:
        from fastapi import FastAPI, File, Form, UploadFile
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import JSONResponse
        import uvicorn
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Serving mode requires fastapi + uvicorn. Install with:\n"
            "pip install fastapi uvicorn python-multipart"
        ) from exc

    app = FastAPI(title="Leaf Disease Classifier")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/predict")
    async def predict_endpoint(file: UploadFile = File(...), top_k: int = Form(3)) -> JSONResponse:
        if not file.content_type or not file.content_type.startswith("image/"):
            return JSONResponse(status_code=400, content={"error": "Only image uploads are supported."})
        image_bytes = await file.read()
        try:
            predictions = predict_from_bytes(image_bytes=image_bytes, labels_json=labels_json, top_k=max(1, top_k))
            return JSONResponse(content={"predictions": predictions})
        except Exception as exc:  # pragma: no cover
            return JSONResponse(status_code=500, content={"error": f"Prediction failed: {exc}"})

    print(f"Starting classifier API at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify leaf disease from an uploaded image.")
    parser.add_argument("--image", required=False, help="Path to uploaded image file.")
    parser.add_argument(
        "--labels-json",
        default=None,
        help="Optional JSON file path containing class labels array in model order.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Number of top classes to print (default: 3).",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Run local HTTP server for frontend integration.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host for --serve mode.")
    parser.add_argument("--port", type=int, default=8010, help="Port for --serve mode.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.serve:
        run_server(host=args.host, port=args.port, labels_json=args.labels_json)
        return
    if not args.image:
        raise ValueError("Use --image for CLI mode, or use --serve for API mode.")
    image_path = Path(args.image)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    predict(image_path=image_path, labels_json=args.labels_json, top_k=max(1, args.top_k))


if __name__ == "__main__":
    main()
