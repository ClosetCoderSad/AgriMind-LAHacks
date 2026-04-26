"""Pydantic models for Cloudinary webhook -> agent pipeline (AgriMind)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NormalizedMediaEvent(BaseModel):
    """Common fields after parsing a Cloudinary notification payload."""

    notification_type: str | None = None
    public_id: str = ""
    resource_type: str = "image"  # "image" | "video" | "raw" | "auto" | ...
    version: int | str | None = None
    format: str | None = None
    width: int | None = None
    height: int | None = None
    bytes: int | None = None
    secure_url: str | None = None
    url: str | None = None
    created_at: str | None = None
    tags: list[str] = Field(default_factory=list)
    # Raw context (string or list) as returned by API
    context: dict[str, str] | list[Any] | str | None = None
    farm_id: str | None = None
    plant_id: str | None = None
    plot_id: str | None = None
    day_index: str | None = None
    capture_date: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class TransformedMediaUrls(BaseModel):
    """URL-based Cloudinary transformations (delivery)."""

    thumbnail: str | None = None
    preview: str | None = None
    overlay: str | None = None
    original_secure_url: str | None = None


class CloudinaryAnalysisOutput(BaseModel):
    """Result stored and returned to ASI:One / webhooks after orchestration."""

    status: str
    event_id: int | None = None
    public_id: str
    resource_type: str
    analysis_summary: str
    risk_labels: list[str] = Field(default_factory=list)
    recommended_action: str = ""
    transformed_media_urls: TransformedMediaUrls
    # Twelve Labs linkage when a video was indexed
    video_id: str | None = None
    index_id: str | None = None
    stream_url: str | None = None
    twelvelabs_error: str | None = None
    sustainability: dict[str, Any] = Field(default_factory=dict)
    # Structured ag analysis when 12L JSON parse succeeds
    analysis: dict[str, Any] | None = None
    health: dict[str, Any] | None = None
    irrigation: dict[str, Any] | None = None
    error: str | None = None

    model_config = ConfigDict(extra="allow")
