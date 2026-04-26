from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import requests

from agrimind.schemas import FusionOutput, GemmaAdvice


class Gemma4Advisor:
    def __init__(self, model_id: Optional[str] = None) -> None:
        # Ollama model tag to run locally on the supercomputer.
        self.model_id = model_id or os.getenv("GEMMA4_OLLAMA_MODEL", "gemma3:4b")
        self.ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
        self.timeout_s = int(os.getenv("OLLAMA_TIMEOUT_S", "180"))
        prompt_path = Path("prompts/gemma4_advice_system.txt")
        self.system_prompt = (
            prompt_path.read_text(encoding="utf-8")
            if prompt_path.exists()
            else "You are an agronomy assistant. Return strict JSON only."
        )

    @staticmethod
    def _prompt(fused: FusionOutput) -> str:
        payload = {
            "scan_id": fused.scan_id,
            "risk_score": fused.risk_score,
            "severity": fused.severity.value,
            "irrigation_flag": fused.irrigation_flag,
            "fertilizer_flag": fused.fertilizer_flag,
            "pest_flag": fused.pest_flag,
            "rationale": fused.rationale,
            "disease_or_stress_label": fused.vlm.disease_or_stress_label,
            "vlm_confidence": fused.vlm.confidence,
            "sensor_values": fused.sensors.model_dump(),
        }
        return f"INPUT_JSON:\n{json.dumps(payload)}"

    @staticmethod
    def _default_payload() -> dict:
        return {
            "summary": "Crop stress detected. Verify field conditions.",
            "confidence_band": "medium",
            "urgency": "moderate",
            "interventions": ["Re-check in field and capture follow-up image."],
            "monitor_after_hours": 12,
            "notes": "Model response parsing fallback used.",
        }

    def _generate_with_ollama(self, prompt: str) -> str:
        endpoint = f"{self.ollama_url.rstrip('/')}/api/generate"
        response = requests.post(
            endpoint,
            json={
                "model": self.model_id,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0},
            },
            timeout=self.timeout_s,
        )
        response.raise_for_status()
        data = response.json()
        return str(data.get("response", "")).strip()

    def advise(self, fused: FusionOutput) -> GemmaAdvice:
        prompt = f"{self.system_prompt}\n\n{self._prompt(fused)}"
        text = self._generate_with_ollama(prompt)
        raw_json = text.split("INPUT_JSON:")[-1].strip()

        # Fallback-safe parse: choose last object-like segment.
        start = raw_json.rfind("{")
        end = raw_json.rfind("}")
        payload = self._default_payload()
        if start != -1 and end != -1 and end > start:
            try:
                payload = json.loads(raw_json[start : end + 1])
            except json.JSONDecodeError:
                pass

        return GemmaAdvice(scan_id=fused.scan_id, **payload)
