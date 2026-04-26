from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime
from uuid import uuid4

from dotenv import load_dotenv
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    ResourceContent,
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
    return json.dumps(payload, ensure_ascii=True, indent=2)


def _cloudinary_latest_text(result: dict) -> str:
    lines = [
        "Cloudinary Latest Analysis",
        "-------------------------",
        f"Event ID: {result.get('event_id', 'n/a')}",
        f"Created At: {result.get('created_at', 'n/a')}",
        f"Asset: {result.get('asset_public_id', 'n/a')} ({result.get('asset_type', 'n/a')})",
        f"Status: {result.get('analysis_status', 'n/a')}",
        f"Summary: {result.get('analysis_summary', 'n/a')}",
        f"Action: {result.get('recommended_action', 'n/a')}",
    ]

    risk_labels = result.get("risk_labels") or []
    lines.append(f"Labels: {', '.join(risk_labels) if risk_labels else 'n/a'}")

    sustainability = result.get("sustainability") or {}
    if isinstance(sustainability, dict):
        water = sustainability.get("water_saved_liters_estimate", "n/a")
        carbon = sustainability.get("carbon_kg_co2e_avoided_estimate", "n/a")
        trips = sustainability.get("avoided_trip_km_estimate", "n/a")
        lines.append(f"Impact: water_saved={water}L, carbon_avoided={carbon}kgCO2e, travel_avoided={trips}km")
        note = sustainability.get("waste_reduction_note")
        if note:
            lines.append(f"Waste Note: {note}")

    media = result.get("media_urls") or {}
    if isinstance(media, dict):
        lines.append("")
        lines.append("Media URLs")
        lines.append(f"- Overlay: {media.get('overlay') or 'n/a'}")
        lines.append(f"- Preview: {media.get('preview') or 'n/a'}")
        lines.append(f"- Thumbnail: {media.get('thumbnail') or 'n/a'}")
        lines.append(f"- Original: {media.get('original') or 'n/a'}")

    return "\n".join(lines)


def _tool_output_text(result: dict) -> str:
    tool = str(result.get("tool", "unknown_tool"))
    status = str(result.get("status", "unknown"))
    lines = [f"Tool: {tool}", f"Status: {status}"]

    if result.get("step"):
        lines.append(f"Step: {result.get('step')}")
    if result.get("video_id"):
        lines.append(f"Video ID: {result.get('video_id')}")
    if result.get("index_id"):
        lines.append(f"Index ID: {result.get('index_id')}")
    if result.get("summary"):
        lines.append(f"Summary: {result.get('summary')}")
    if result.get("search_reference"):
        lines.append(f"Search Ref: {result.get('search_reference')}")
    if result.get("stream_url"):
        lines.append(f"Stream URL: {result.get('stream_url')}")
    if result.get("question"):
        lines.append(f"Question: {result.get('question')}")

    result_text = result.get("result_text")
    if isinstance(result_text, str) and result_text.strip():
        lines.append("")
        lines.append("Analysis")
        lines.append("--------")
        lines.append(result_text.strip())

    next_action = result.get("next_action")
    if isinstance(next_action, str) and next_action.strip():
        lines.append("")
        lines.append(f"Next Action: {next_action.strip()}")

    error = result.get("error")
    if error:
        lines.append(f"Error: {error}")

    return "\n".join(lines)


def _tool_help_text() -> str:
    return (
        "Send JSON with one of these tools: "
        "twelvelabs.ingest_video, twelvelabs.summarize_video, twelvelabs.ask_video, twelvelabs.analyze_video, "
        "agri.cloudinary_latest, agri.cloudinary_analyze_uri. "
        "agri.cloudinary_latest requires AGRIMIND_API_BASE to point at the FastAPI server and returns the most recent "
        "Cloudinary webhook + AI analysis (sustainability + transform URLs + TwelveLabs when enabled). "
        "agri.cloudinary_analyze_uri uploads a public image/video URL to Cloudinary and runs the same analysis pipeline. "
        "Example: "
        '{"tool":"twelvelabs.analyze_video","args":{"video_url":"https://.../sample.mp4"}} '
        'or {"tool":"agri.cloudinary_latest","args":{}} '
        'or {"tool":"agri.cloudinary_analyze_uri","args":{"uri":"https://.../image.webp"}}'
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

    if tool_name == "agri.cloudinary_latest":
        base = (os.getenv("AGRIMIND_API_BASE", "http://127.0.0.1:8000") or "").rstrip("/")
        url = f"{base}/api/cloudinary/latest"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=25) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            return {
                "status": "failed",
                "tool": tool_name,
                "error": str(exc),
                "hint": "Set AGRIMIND_API_BASE to your FastAPI public URL; ensure the API is running and /api/cloudinary has received at least one webhook event.",
            }
        except Exception as exc:  # pragma: no cover
            return {"status": "failed", "tool": tool_name, "error": str(exc)}
        if isinstance(payload, dict) and payload.get("status") == "ok" and isinstance(payload.get("result"), dict):
            latest = payload.get("result") or {}
            media_urls = latest.get("transformed_media_urls") or {}
            clean = {
                "status": "success",
                "tool": tool_name,
                "event_id": payload.get("id"),
                "created_at": payload.get("created_at"),
                "asset_public_id": latest.get("public_id"),
                "asset_type": latest.get("resource_type"),
                "analysis_status": latest.get("status"),
                "analysis_summary": latest.get("analysis_summary"),
                "recommended_action": latest.get("recommended_action"),
                "risk_labels": latest.get("risk_labels") or [],
                "sustainability": latest.get("sustainability") or {},
                "media_urls": {
                    "overlay": media_urls.get("overlay"),
                    "preview": media_urls.get("preview"),
                    "thumbnail": media_urls.get("thumbnail"),
                    "original": media_urls.get("original_secure_url"),
                },
            }
            return {
                "status": "success",
                "tool": tool_name,
                "format": "text",
                "text": _cloudinary_latest_text(clean),
                "data": clean,
            }
        return {
            "status": "success",
            "tool": tool_name,
            "result": payload,
        }

    if tool_name == "agri.cloudinary_analyze_uri":
        uri = str(args.get("uri", "")).strip()
        resource_type = str(args.get("resource_type", "image")).strip() or "image"
        if not uri:
            return {"status": "failed", "tool": tool_name, "error": "missing_uri"}
        base = (os.getenv("AGRIMIND_API_BASE", "http://127.0.0.1:8000") or "").rstrip("/")
        url = f"{base}/api/cloudinary/analyze-uri"
        body = json.dumps({"uri": uri, "resource_type": resource_type}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            return {
                "status": "failed",
                "tool": tool_name,
                "error": str(exc),
                "hint": "Ensure AGRIMIND_API_BASE is reachable and backend /api/cloudinary/analyze-uri is running.",
            }
        except Exception as exc:  # pragma: no cover
            return {"status": "failed", "tool": tool_name, "error": str(exc)}
        # Reuse latest formatter for consistency.
        return {
            "status": "success",
            "tool": tool_name,
            "format": "text",
            "text": (
                "Cloudinary URI Analysis Complete\n"
                "-------------------------------\n"
                f"Status: {payload.get('status', 'n/a')}\n"
                f"Public ID: {payload.get('public_id', 'n/a')}\n"
                f"Summary: {payload.get('analysis_summary', 'n/a')}\n"
                f"Action: {payload.get('recommended_action', 'n/a')}\n"
                "Media URLs\n"
                f"- Original: {(payload.get('transformed_media_urls') or {}).get('original_secure_url', 'n/a')}\n"
                f"- Preview: {(payload.get('transformed_media_urls') or {}).get('preview', 'n/a')}\n"
                f"- Thumbnail: {(payload.get('transformed_media_urls') or {}).get('thumbnail', 'n/a')}\n"
                f"- Overlay: {(payload.get('transformed_media_urls') or {}).get('overlay', 'n/a')}"
            ),
            "data": payload,
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


def _extract_first_http_url(text: str) -> str | None:
    match = re.search(r"https?://\S+", text)
    if not match:
        return None
    candidate = match.group(0).strip().rstrip(".,);")
    return candidate or None


def _guess_resource_type_from_text(text: str) -> str:
    t = text.lower()
    if any(ext in t for ext in [".mp4", ".mov", ".webm", ".mkv"]) or "video" in t:
        return "video"
    return "image"


def _extract_resource_uri_from_content(msg: ChatMessage) -> tuple[str | None, str | None]:
    for item in msg.content:
        if isinstance(item, ResourceContent):
            resource_obj = item.resource
            primary = resource_obj[0] if isinstance(resource_obj, list) and resource_obj else resource_obj
            uri = getattr(primary, "uri", None)
            metadata = getattr(primary, "metadata", {}) or {}
            mime = str(metadata.get("mime_type", "")).lower() if isinstance(metadata, dict) else ""
            if uri:
                if mime.startswith("video/"):
                    return str(uri), "video"
                return str(uri), "image"
    return None, None


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
    resource_uri, resource_type = _extract_resource_uri_from_content(msg)

    response_text = _tool_help_text()

    try:
        if resource_uri:
            response = _run_tool(
                {
                    "tool": "agri.cloudinary_analyze_uri",
                    "args": {"uri": resource_uri, "resource_type": resource_type or "image"},
                }
            )
            if (
                isinstance(response, dict)
                and str(response.get("format", "")).lower() == "text"
                and isinstance(response.get("text"), str)
            ):
                response_text = str(response.get("text"))
            else:
                response_text = _json_text(response if isinstance(response, dict) else {"status": "failed"})
            raise RuntimeError("handled_resource_flow")

        payload = _extract_json_payload(user_text)
        if isinstance(payload, dict) and payload.get("tool"):
            tool_output = _run_tool(payload)
            if (
                isinstance(tool_output, dict)
                and str(tool_output.get("format", "")).lower() == "text"
                and isinstance(tool_output.get("text"), str)
            ):
                response_text = str(tool_output.get("text"))
            elif isinstance(tool_output, dict):
                response_text = _tool_output_text(tool_output)
            else:
                response_text = _json_text(tool_output if isinstance(tool_output, dict) else {"status": "failed"})
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
        else:
            # Natural language (non-JSON) fallbacks.
            text_lower = user_text.lower()
            maybe_uri = _extract_first_http_url(user_text)
            if maybe_uri and "cloudinary" in text_lower and any(
                k in text_lower for k in ["analy", "overlay", "upload", "image", "video"]
            ):
                output = _run_tool(
                    {
                        "tool": "agri.cloudinary_analyze_uri",
                        "args": {"uri": maybe_uri, "resource_type": _guess_resource_type_from_text(user_text)},
                    }
                )
                if (
                    isinstance(output, dict)
                    and str(output.get("format", "")).lower() == "text"
                    and isinstance(output.get("text"), str)
                ):
                    response_text = str(output.get("text"))
                else:
                    response_text = _json_text(output if isinstance(output, dict) else {"status": "failed"})
            elif "cloudinary" in text_lower and (
                "latest" in text_lower or "overlay" in text_lower or "analy" in text_lower
            ):
                output = _run_tool({"tool": "agri.cloudinary_latest", "args": {}})
                if (
                    isinstance(output, dict)
                    and str(output.get("format", "")).lower() == "text"
                    and isinstance(output.get("text"), str)
                ):
                    response_text = str(output.get("text"))
                else:
                    response_text = _json_text(output if isinstance(output, dict) else {"status": "failed"})
    except Exception as exc:
        if str(exc) != "handled_resource_flow":
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
