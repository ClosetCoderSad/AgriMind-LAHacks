from __future__ import annotations

import json
import os
import re
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
from backend.services.twelvelabs_client import TwelveLabsClientService

load_dotenv()

agent = Agent(
    name="agrimind-orchestrator-agent",
    seed=os.getenv("ORCHESTRATOR_SEED_PHRASE", "replace_with_unique_random_string"),
    port=int(os.getenv("ORCHESTRATOR_PORT", "8010")),
    mailbox=os.getenv("ENABLE_MAILBOX", "true").lower() == "true",
    publish_agent_details=os.getenv("PUBLISH_AGENT_DETAILS", "true").lower() == "true",
)

protocol = Protocol(spec=chat_protocol_spec)


def _json_text(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=True)


def _tool_help_text() -> str:
    return (
        "Send JSON with one of these tools: "
        "twelvelabs.ingest_video, twelvelabs.summarize_video, twelvelabs.ask_video, twelvelabs.analyze_video. "
        "Example: "
        '{"tool":"twelvelabs.analyze_video","args":{"video_url":"https://.../sample.mp4"}}'
    )


def _run_tool(payload: dict) -> dict:
    service = TwelveLabsClientService()
    tool_name = str(payload.get("tool", "")).strip()
    args = payload.get("args") or {}
    if not isinstance(args, dict):
        return {"status": "failed", "error": "args_must_be_object"}

    if tool_name == "twelvelabs.ingest_video":
        video_url = str(args.get("video_url", "")).strip()
        if not video_url:
            return {"status": "failed", "error": "missing_video_url"}
        result = service.ingest_video_url(video_url)
        return {
            "status": result.status,
            "tool": tool_name,
            "summary": result.summary,
            "video_id": result.video_id,
            "index_id": result.index_id,
            "stream_url": result.stream_url,
            "search_reference": result.search_reference,
            "error": result.error,
        }

    if tool_name == "twelvelabs.summarize_video":
        video_id = str(args.get("video_id", "")).strip()
        prompt = args.get("prompt")
        if not video_id:
            return {"status": "failed", "error": "missing_video_id"}
        result = service.summarize_video(video_id=video_id, prompt=(str(prompt) if prompt else None))
        return {
            "status": result.status,
            "tool": tool_name,
            "video_id": video_id,
            "result_text": result.text,
            "error": result.error,
        }

    if tool_name == "twelvelabs.ask_video":
        video_id = str(args.get("video_id", "")).strip()
        question = str(args.get("question", "")).strip()
        if not video_id:
            return {"status": "failed", "error": "missing_video_id"}
        if not question:
            return {"status": "failed", "error": "missing_question"}
        result = service.ask_video(video_id=video_id, question=question)
        return {
            "status": result.status,
            "tool": tool_name,
            "video_id": video_id,
            "question": question,
            "result_text": result.text,
            "error": result.error,
        }

    if tool_name == "twelvelabs.analyze_video":
        video_id = str(args.get("video_id", "")).strip()
        video_url = str(args.get("video_url", "")).strip()
        prompt = args.get("prompt")
        if not video_id and not video_url:
            return {"status": "failed", "error": "missing_video_id_or_video_url"}

        if not video_id and video_url:
            ingestion = service.ingest_video_url(video_url)
            if ingestion.status != "ready" or not ingestion.video_id:
                return {
                    "status": ingestion.status,
                    "tool": tool_name,
                    "step": "ingestion",
                    "summary": ingestion.summary,
                    "video_id": ingestion.video_id,
                    "search_reference": ingestion.search_reference,
                    "error": ingestion.error,
                    "next_action": "Retry with returned video_id once indexing is ready.",
                }
            video_id = ingestion.video_id

        summary_result = service.summarize_video(
            video_id=video_id,
            prompt=(str(prompt) if prompt else "Summarize crop health and irrigation implications."),
        )
        return {
            "status": summary_result.status,
            "tool": tool_name,
            "step": "summary",
            "video_id": video_id,
            "result_text": summary_result.text,
            "error": summary_result.error,
        }

    return {"status": "failed", "error": f"unsupported_tool:{tool_name}"}


def _extract_json_payload(raw_text: str) -> dict | None:
    text = raw_text.strip()
    if not text:
        return None

    # Handle markdown code fences frequently added by chat clients.
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, count=1, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text, count=1)
        text = text.strip()

    # Fast path: whole message is JSON.
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass

    # Fallback: extract the first JSON object from noisy wrapper text.
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None

    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


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

    response_text = _tool_help_text()

    try:
        payload = _extract_json_payload(user_text)
        if isinstance(payload, dict) and payload.get("tool"):
            response_text = _json_text(_run_tool(payload))
        elif isinstance(payload, dict):
            request = DecisionRequest.model_validate(payload)
            decision = run_agri_pipeline(request)
            response_text = _json_text(
                {
                    "status": "success",
                    "tool": "agri.decision",
                    "action": decision.action,
                    "disease": decision.disease,
                    "recommendation": decision.recommendation,
                    "water_saved_ml": decision.impact.water_saved_ml,
                    "risk_level": decision.impact.risk_level,
                }
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
