from __future__ import annotations

import json
import os
from datetime import datetime
from uuid import uuid4

from dotenv import load_dotenv
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    TextContent,
    chat_protocol_spec,
)

from backend.models.contracts import DecisionRequest
from backend.services.pipeline import run_agri_pipeline

load_dotenv()

agent = Agent(
    name="agrimind-orchestrator-agent",
    seed=os.getenv("ORCHESTRATOR_SEED_PHRASE", "replace_with_unique_random_string"),
    port=int(os.getenv("ORCHESTRATOR_PORT", "8010")),
    mailbox=os.getenv("ENABLE_MAILBOX", "true").lower() == "true",
    publish_agent_details=os.getenv("PUBLISH_AGENT_DETAILS", "true").lower() == "true",
)

protocol = Protocol(spec=chat_protocol_spec)


@protocol.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage) -> None:
    await ctx.send(
        sender,
        ChatAcknowledgement(
            timestamp=datetime.utcnow(),
            acknowledged_msg_id=msg.msg_id,
        ),
    )

    text_chunks: list[str] = []
    for item in msg.content:
        if isinstance(item, TextContent):
            text_chunks.append(item.text)

    user_text = " ".join(text_chunks).strip()

    response_text = (
        "Send a JSON payload with keys sensors, crop_stage, rain_chance and optional image to get an AgriMind decision."
    )

    try:
        payload = json.loads(user_text)
        request = DecisionRequest.model_validate(payload)
        decision = run_agri_pipeline(request)
        response_text = (
            f"Action: {decision.action}. "
            f"Disease: {decision.disease}. "
            f"Recommendation: {decision.recommendation}. "
            f"Water saved: {decision.impact.water_saved_ml}ml."
        )
    except Exception as exc:
        ctx.logger.info("Orchestrator received non-JSON or invalid payload: %s", exc)

    await ctx.send(
        sender,
        ChatMessage(
            timestamp=datetime.utcnow(),
            msg_id=uuid4(),
            content=[
                TextContent(type="text", text=response_text),
                EndSessionContent(type="end-session"),
            ],
        ),
    )


@protocol.on_message(ChatAcknowledgement)
async def handle_ack(_: Context, __: str, ___: ChatAcknowledgement) -> None:
    return


agent.include(protocol, publish_manifest=True)


if __name__ == "__main__":
    agent.run()
