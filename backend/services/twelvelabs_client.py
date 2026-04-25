from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class TwelveLabsIngestionResult:
    status: str
    summary: str
    index_id: str | None = None
    asset_id: str | None = None
    indexed_asset_id: str | None = None
    video_id: str | None = None
    stream_url: str | None = None
    search_reference: str | None = None
    error: str | None = None


@dataclass
class TwelveLabsVideoRef:
    video_id: str
    index_id: str
    filename: str | None = None
    duration: float | None = None
    created_at: str | None = None
    stream_url: str | None = None


@dataclass
class TwelveLabsTextResult:
    status: str
    text: str | None = None
    error: str | None = None


class TwelveLabsClientService:
    def __init__(self) -> None:
        self.enabled = os.getenv("TWELVELABS_ENABLED", "false").lower() == "true"
        self.api_key = os.getenv("TWELVELABS_API_KEY", "").strip()
        self.index_id = os.getenv("TWELVELABS_INDEX_ID", "").strip()
        self.poll_interval_sec = int(os.getenv("TWELVELABS_POLL_INTERVAL_SEC", "5"))
        self.max_poll_attempts = int(os.getenv("TWELVELABS_MAX_POLL_ATTEMPTS", "30"))

    def _obj_id(self, obj: Any) -> str | None:
        return getattr(obj, "id", None) or getattr(obj, "_id", None)

    def _obj_status(self, obj: Any) -> str | None:
        status = getattr(obj, "status", None)
        if isinstance(status, str):
            return status
        if status is None:
            return None
        return str(status)

    def _obj_attr(self, obj: Any, *names: str) -> str | None:
        for name in names:
            value = getattr(obj, name, None)
            if value:
                return str(value)
        return None

    def _extract_stream_url(self, obj: Any) -> str | None:
        if obj is None:
            return None

        direct = self._obj_attr(obj, "stream_url", "video_stream_url", "video_url")
        if direct:
            return direct

        hls = getattr(obj, "hls", None)
        if hls is None:
            return None

        if isinstance(hls, str):
            return hls

        hls_url = getattr(hls, "video_url", None) or getattr(hls, "stream_url", None)
        if hls_url:
            return str(hls_url)

        return None

    def _status_is_ready(self, status: str | None) -> bool:
        return status in {"ready", "completed", "done"}

    def _status_is_failed(self, status: str | None) -> bool:
        return status in {"failed", "error"}

    def _build_client(self):
        if not self.enabled:
            return None, TwelveLabsTextResult(status="disabled", error="twelvelabs_disabled")
        if not self.api_key:
            return None, TwelveLabsTextResult(status="failed", error="missing_api_key")
        try:
            from twelvelabs import TwelveLabs

            return TwelveLabs(api_key=self.api_key), None
        except Exception as exc:  # pragma: no cover
            return None, TwelveLabsTextResult(status="failed", error=str(exc))

    def _resolve_index_id(self, index_id: str | None) -> str | None:
        candidate = (index_id or self.index_id or "").strip()
        return candidate or None

    def ingest_video_url(self, video_url: str) -> TwelveLabsIngestionResult:
        if not self.enabled:
            return TwelveLabsIngestionResult(status="disabled", summary="TwelveLabs integration is disabled.")

        if not self.api_key:
            return TwelveLabsIngestionResult(status="failed", summary="TwelveLabs API key is missing.", error="missing_api_key")

        if not self.index_id:
            return TwelveLabsIngestionResult(status="failed", summary="TWELVELABS_INDEX_ID is missing.", error="missing_index_id")

        if not video_url:
            return TwelveLabsIngestionResult(status="skipped", summary="No video URL available for ingestion.")

        try:
            client, client_error = self._build_client()
            if client_error or client is None:
                return TwelveLabsIngestionResult(
                    status=(client_error.status if client_error else "failed"),
                    summary="TwelveLabs client initialization failed.",
                    index_id=self.index_id,
                    error=(client_error.error if client_error else "client_init_failed"),
                )

            task = client.tasks.create(
                index_id=self.index_id,
                video_url=video_url,
                enable_video_stream=True,
            )
            task_id = self._obj_id(task)
            if not task_id:
                return TwelveLabsIngestionResult(
                    status="failed",
                    summary="TwelveLabs task creation failed to return a task id.",
                    index_id=self.index_id,
                    error="missing_task_id",
                )

            final_task = task
            if hasattr(client.tasks, "wait_for_done"):
                final_task = client.tasks.wait_for_done(
                    task_id,
                    sleep_interval=float(self.poll_interval_sec),
                )

            status = self._obj_status(final_task) or "processing"
            video_id = self._obj_attr(final_task, "video_id")
            asset_id = self._obj_attr(final_task, "asset_id")
            stream_url = None

            if video_id:
                try:
                    video_details = client.indexes.videos.retrieve(self.index_id, video_id)
                    stream_url = self._extract_stream_url(video_details)
                except Exception:
                    stream_url = None

            search_reference = (
                f"index_id={self.index_id};video_id={video_id}"
                if video_id
                else f"index_id={self.index_id};task_id={task_id}"
            )

            if self._status_is_ready(status):
                return TwelveLabsIngestionResult(
                    status="ready",
                    summary="Video indexed successfully in TwelveLabs.",
                    index_id=self.index_id,
                    asset_id=asset_id,
                    indexed_asset_id=task_id,
                    video_id=video_id,
                    stream_url=stream_url,
                    search_reference=search_reference,
                )

            if self._status_is_failed(status):
                return TwelveLabsIngestionResult(
                    status="failed",
                    summary="TwelveLabs indexing task failed.",
                    index_id=self.index_id,
                    asset_id=asset_id,
                    indexed_asset_id=task_id,
                    video_id=video_id,
                    search_reference=search_reference,
                    error=self._obj_attr(final_task, "error", "message") or "task_failed",
                )

            return TwelveLabsIngestionResult(
                status="processing",
                summary="TwelveLabs task is still processing.",
                index_id=self.index_id,
                asset_id=asset_id,
                indexed_asset_id=task_id,
                video_id=video_id,
                stream_url=stream_url,
                search_reference=search_reference,
            )

        except Exception as exc:  # pragma: no cover
            return TwelveLabsIngestionResult(
                status="failed",
                summary="TwelveLabs ingestion failed due to runtime error.",
                index_id=self.index_id,
                error=str(exc),
            )

    def list_index_videos(self, index_id: str | None = None, limit: int = 20) -> tuple[list[TwelveLabsVideoRef], str | None]:
        resolved_index_id = self._resolve_index_id(index_id)
        if not resolved_index_id:
            return [], "missing_index_id"

        client, client_error = self._build_client()
        if client_error or client is None:
            return [], (client_error.error if client_error else "client_init_failed")

        try:
            pager = client.indexes.videos.list(resolved_index_id, page_limit=max(1, min(limit, 50)))
            videos: list[TwelveLabsVideoRef] = []
            for item in pager:
                video_id = self._obj_id(item)
                if not video_id:
                    continue
                videos.append(
                    TwelveLabsVideoRef(
                        video_id=video_id,
                        index_id=resolved_index_id,
                        filename=self._obj_attr(item, "filename", "name"),
                        duration=float(self._obj_attr(item, "duration") or 0) or None,
                        created_at=self._obj_attr(item, "created_at"),
                        stream_url=self._extract_stream_url(item),
                    )
                )
            return videos, None
        except Exception as exc:  # pragma: no cover
            return [], str(exc)

    def summarize_video(
        self,
        video_id: str,
        summary_type: str = "summary",
        prompt: str | None = None,
    ) -> TwelveLabsTextResult:
        client, client_error = self._build_client()

        if client_error or client is None:
            return TwelveLabsTextResult(
                status=(client_error.status if client_error else "failed"),
                error=(client_error.error if client_error else "client_init_failed"),
            )

        try:
            # Keep this call API-compatible with current TwelveLabs SDK variants.
            response = client.analyze(
                video_id=video_id,
                prompt=prompt or "Summarize this video focusing on agricultural insights.",
            )

            text = (
                self._obj_attr(response, "summary")
                or self._obj_attr(response, "text")
                or self._obj_attr(response, "data")
            )

            if not text:
                chapters = getattr(response, "chapters", None)
                highlights = getattr(response, "highlights", None)

                if chapters:
                    text = "\n".join(
                        getattr(c, "headline", "")
                        for c in chapters
                        if getattr(c, "headline", None)
                    )
                elif highlights:
                    text = "\n".join(
                        getattr(h, "text", "")
                        for h in highlights
                        if getattr(h, "text", None)
                    )

            return TwelveLabsTextResult(
                status="ready",
                text=text or "No summary text returned.",
            )

        except Exception as exc:
            return TwelveLabsTextResult(
                status="failed",
                error=str(exc),
            )

    def ask_video(self, video_id: str, question: str) -> TwelveLabsTextResult:
        client, client_error = self._build_client()
        if client_error or client is None:
            return TwelveLabsTextResult(
                status=(client_error.status if client_error else "failed"),
                error=(client_error.error if client_error else "client_init_failed"),
            )

        if not question.strip():
            return TwelveLabsTextResult(status="failed", error="missing_question")

        try:
            response = client.analyze(video_id=video_id, prompt=question.strip())
            text = self._obj_attr(response, "data", "text", "analysis")
            if not text:
                content = getattr(response, "data", None)
                if content is not None:
                    text = str(content)
            return TwelveLabsTextResult(status="ready", text=text or "No answer text returned.")
        except Exception as exc:  # pragma: no cover
            return TwelveLabsTextResult(status="failed", error=str(exc))
