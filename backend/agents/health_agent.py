from __future__ import annotations

import os

from dotenv import load_dotenv
from uagents import Agent, Context, Model

from backend.models.contracts import DiagnosisResult, ImageSignal
from backend.services.health_intelligence import build_health_agent_output

load_dotenv()


class HealthRequest(Model):
    disease: str
    confidence: float
    plant_type: str = "tomato"
    image_public_id: str | None = None
    image_format: str | None = None
    image_width: int | None = None
    image_height: int | None = None
    image_bytes: int | None = None


class HealthResponse(Model):
    disease: str
    severity: str
    diagnosis_confidence: float
    explanation: str
    visual_history_url: str | None = None
    twelvelabs_summary: str | None = None


agent = Agent(
    name="agrimind-health-agent",
    seed=os.getenv("HEALTH_SEED_PHRASE", "replace_with_unique_random_string"),
    port=int(os.getenv("HEALTH_AGENT_PORT", "8011")),
    mailbox=os.getenv("ENABLE_MAILBOX", "true").lower() == "true",
    publish_agent_details=os.getenv("PUBLISH_AGENT_DETAILS", "true").lower() == "true",
)


@agent.on_message(model=HealthRequest)
async def handle_health(ctx: Context, sender: str, msg: HealthRequest) -> None:
    image = None
    if (
        msg.image_public_id
        and msg.image_format
        and msg.image_width is not None
        and msg.image_height is not None
        and msg.image_bytes is not None
    ):
        image = ImageSignal(
            public_id=msg.image_public_id,
            format=msg.image_format,
            width=msg.image_width,
            height=msg.image_height,
            bytes=msg.image_bytes,
        )

    diagnosis = DiagnosisResult(
        disease=msg.disease,
        confidence=msg.confidence,
        urgency="high" if msg.confidence >= 0.85 else "medium" if msg.confidence >= 0.7 else "low",
        actions=[],
    )

    health_output = build_health_agent_output(
        diagnosis=diagnosis,
        image=image,
        plant_type=msg.plant_type,
    )

    await ctx.send(
        sender,
        HealthResponse(
            disease=health_output.disease,
            severity=health_output.severity,
            diagnosis_confidence=health_output.diagnosis_confidence,
            explanation=health_output.explanation,
            visual_history_url=health_output.visual_history_url,
            twelvelabs_summary=health_output.twelvelabs_summary,
        ),
    )


if __name__ == "__main__":
    agent.run()
