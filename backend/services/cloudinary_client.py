"""
Cloudinary notification verification and URL-based transformations.
See: https://cloudinary.com/documentation/notification_signatures
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Any
from urllib.parse import parse_qs, unquote, quote, urlparse
from xml.etree import ElementTree

from backend.models.cloudinary_contracts import NormalizedMediaEvent, TransformedMediaUrls


def _get_env() -> dict[str, str | bool | int]:
    return {
        "cloud_name": (os.getenv("CLOUDINARY_CLOUD_NAME", "") or "").strip(),
        "api_secret": (os.getenv("CLOUDINARY_API_SECRET", "") or "").strip(),
        "skip_verify": (os.getenv("CLOUDINARY_WEBHOOK_SKIP_VERIFY", "false").lower() == "true"),
        "max_timestamp_age_sec": int(os.getenv("CLOUDINARY_WEBHOOK_MAX_AGE_SEC", "7200")),
    }


def verify_notification_signature(
    raw_body: bytes,
    x_cld_timestamp: str | None,
    x_cld_signature: str | None,
) -> bool:
    """
    Verify X-Cld-Signature against the raw request body.
    String to hash: body (string) + timestamp + api_secret, then SHA-1 or SHA-256 hex digest.
    """
    cfg = _get_env()
    if cfg["skip_verify"]:
        return True
    if not cfg["api_secret"] or not x_cld_timestamp or not x_cld_signature:
        return False

    try:
        ts = int(x_cld_timestamp)
    except (TypeError, ValueError):
        return False

    now = int(time.time())
    if abs(now - ts) > int(cfg["max_timestamp_age_sec"]):
        return False

    body_str: str
    try:
        body_str = raw_body.decode("utf-8")
    except UnicodeDecodeError:
        body_str = raw_body.decode("latin-1", errors="replace")

    secret = str(cfg["api_secret"])
    to_hash = f"{body_str}{x_cld_timestamp}{secret}"
    payload = to_hash.encode("utf-8")
    sha1_hex = hashlib.sha1(payload).hexdigest()
    if sha1_hex == x_cld_signature.lower().strip():
        return True
    sha256_hex = hashlib.sha256(payload).hexdigest()
    if sha256_hex == x_cld_signature.lower().strip():
        return True
    return False


def _split_tags(s: str | None) -> list[str]:
    if not s or not s.strip():
        return []
    # Cloudinary may use comma; space also appears in some clients
    parts: list[str] = []
    for p in s.replace(" ", ",").split(","):
        t = p.strip()
        if t:
            parts.append(t)
    return parts


def _context_from_key_value(s: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in s.split("|"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            k, v = k.strip(), v.strip()
            if k:
                out[k] = v
    return out


def parse_notification_body(raw_body: bytes, content_type: str | None) -> dict[str, Any]:
    """
    Cloudinary may POST application/x-www-form-urlencoded, JSON, or (rarely) XML.
    Return a flat dict of common parameters.
    """
    ct = (content_type or "").lower()
    if "application/json" in ct or raw_body.strip().startswith(b"{"):
        return json.loads(raw_body.decode("utf-8", errors="replace"))
    if "application/xml" in ct or "text/xml" in ct or raw_body.strip().startswith(b"<?xml"):
        root = ElementTree.fromstring(raw_body.decode("utf-8", errors="replace"))  # noqa: S314
        text = (root.text or "").strip() if len(root) == 0 else ""
        if not text and len(root) > 0:
            text = (root[0].text or "").strip()
        # Fallback: convert simple element tree to string dict
        def iter_flat(el: Any, prefix: str = "") -> dict[str, str]:
            acc: dict[str, str] = {}
            for child in el:  # type: ignore[assignment]
                key = f"{prefix}{child.tag}" if not prefix else f"{prefix}_{child.tag}"
                if list(child):
                    acc.update(iter_flat(child, key))
                elif (child.text or "").strip():
                    acc[key] = (child.text or "").strip()
            return acc

        d = {root.tag: root.text} if (root.text or "").strip() else iter_flat(root)
        return d if d else {"raw": text}

    # Default: form-urlencoded
    qs = parse_qs(raw_body.decode("utf-8", errors="replace"), keep_blank_values=True)
    flat: dict[str, str] = {}
    for k, vlist in qs.items():
        if not vlist:
            continue
        if k == "tags" and len(vlist) > 1:
            flat[k] = ",".join(unquote(x) for x in vlist)
        elif len(vlist) == 1:
            flat[k] = unquote(vlist[0])
    return flat if flat else {"raw": raw_body.decode("utf-8", errors="replace")}


def normalize_to_media_event(flat: dict[str, Any]) -> NormalizedMediaEvent:
    """Map notification dict into NormalizedMediaEvent, including custom context for progression."""
    # Flatten nested "cloudinary" key if present
    if "cloudinary" in flat and isinstance(flat["cloudinary"], dict):
        inner = flat["cloudinary"]
        for k, v in inner.items():
            flat.setdefault(k, v)
    if "data" in flat and isinstance(flat["data"], dict) and "public_id" in flat["data"]:
        d = flat["data"]
        for k, v in d.items():
            flat.setdefault(k, v)

    public_id = str(
        flat.get("public_id")
        or flat.get("publicid")
        or flat.get("PublicID")
        or flat.get("publicId")
        or ""
    )
    rtype_raw = str(
        flat.get("resource_type")
        or flat.get("ResourceType")
        or flat.get("type")
        or "image"
    )
    rlow = rtype_raw.lower()
    if rlow in {"video", "v", "mp4", "mpg", "mpg2", "webm", "mkv", "mov"} or "video" in rlow:
        rtype = "video"
    elif rlow in ("image", "raw", "auto") or "image" in rlow:
        rtype = rlow if rlow in ("image", "raw", "auto") else "image"
    else:
        rtype = "image"

    tags: list[str] = []
    raw_tags = flat.get("tags")
    if isinstance(raw_tags, str):
        tags = _split_tags(raw_tags)
    elif isinstance(raw_tags, list):
        tags = [str(t) for t in raw_tags if t]

    ctx: dict[str, str] = {}
    raw_context = flat.get("context")
    if isinstance(raw_context, dict):
        ctx = {str(k): str(v) for k, v in raw_context.items()}  # type: ignore[misc]
    elif isinstance(raw_context, str) and raw_context.strip():
        if "|" in raw_context or (raw_context.count("=") > 0 and " " not in raw_context):
            ctx = _context_from_key_value(raw_context)
        else:
            ctx = {"raw": raw_context}
    if isinstance(flat.get("phash"), str) and (str(flat.get("phash")).strip()):
        ctx = dict(ctx)
        ctx["phash"] = str(flat.get("phash", ""))

    # common context custom keys
    for key in ("farm_id", "plant_id", "plot_id", "day_index", "capture_date"):
        if key in flat and flat[key]:
            ctx[key] = str(flat[key])

    secure_url = _coerce_url(flat.get("secure_url") or flat.get("full_url") or flat.get("url"))
    v = flat.get("version")
    version: int | str | None
    if v is None or v == "":
        version = None
    elif isinstance(v, (int, float)):
        version = int(v)
    elif isinstance(v, str) and v.strip().isdigit():
        version = int(v)
    else:
        version = str(v)

    return NormalizedMediaEvent(
        notification_type=coerce_str(flat.get("notification_type") or flat.get("action")),
        public_id=public_id,
        resource_type=rtype,
        version=version,
        format=coerce_str(flat.get("format")),
        width=coerce_int(flat.get("width")),
        height=coerce_int(flat.get("height")),
        bytes=coerce_int(flat.get("bytes")),
        secure_url=secure_url,
        url=_coerce_url(flat.get("url")),
        created_at=coerce_str(flat.get("created_at")),
        tags=tags,
        context=ctx or (context_from_flat(flat) or None),
        farm_id=ctx.get("farm_id") or coerce_str(flat.get("farm_id")),
        plant_id=ctx.get("plant_id") or coerce_str(flat.get("plant_id")),
        plot_id=ctx.get("plot_id") or coerce_str(flat.get("plot_id")),
        day_index=ctx.get("day_index") or coerce_str(flat.get("day_index")),
        capture_date=ctx.get("capture_date") or coerce_str(flat.get("capture_date")),
        raw={k: v for k, v in flat.items()},
    )


def context_from_flat(flat: dict[str, Any]) -> dict[str, str] | None:
    """If keys look like agri context, collect them."""
    out: dict[str, str] = {}
    for k, v in flat.items():
        if k in {
            "farm_id",
            "plot_id",
            "plant_id",
            "day_index",
            "capture_date",
        } and v is not None and str(v).strip():
            out[k] = str(v)
    return out or None


def coerce_str(x: Any) -> str | None:
    if x is None:
        return None
    s = str(x).strip()
    return s or None


def coerce_int(x: Any) -> int | None:
    if x is None or x == "":
        return None
    try:
        return int(float(str(x)))
    except (TypeError, ValueError):
        return None


def _coerce_url(x: Any) -> str | None:
    s = coerce_str(x)
    if not s:
        return None
    if s.startswith("http://") or s.startswith("https://"):
        return s
    if s.startswith("//"):
        return f"https:{s}"
    return s


def build_transformation_urls(
    public_id: str,
    resource_type: str,
    version: int | str | None,
    overlay_risk: str = "MEDIUM",
    overlay_moisture: str = "n/a",
    overlay_labels: str | None = None,
    cloud_name: str | None = None,
) -> TransformedMediaUrls:
    """
    Programmable delivery URLs: thumbnail, preview, optional text overlay.
    public_id can include path segments; safe for res.cloudinary.com.
    """
    cloud = (cloud_name or os.getenv("CLOUDINARY_CLOUD_NAME", "") or "").strip()
    if not cloud or not public_id:
        return TransformedMediaUrls(overlay=None, thumbnail=None, preview=None, original_secure_url=None)

    rt = (resource_type or "image").lower()
    if rt in {"v", "video"} or "video" in rt:
        rt = "video"
    elif "image" in rt or rt in {"jpg", "jpeg", "png", "gif", "webp", "heic", "tiff", "bmp", "avif", "ai"}:
        rt = "image"
    else:
        rt = "raw" if rt == "raw" else "image"

    vseg = f"v{version}/" if version is not None and str(version) not in ("", "None") else ""
    public_path = quote(public_id, safe="/")

    base_path = f"{rt}/upload"
    th_t = f"c_limit,h_200,w_200,q_auto:good"
    pr_t = f"c_fill,h_480,w_800,q_auto:good" if rt == "video" else f"c_limit,h_480,w_800,q_auto:best"

    def join_url(t: str) -> str:
        return f"https://res.cloudinary.com/{cloud}/{base_path}/{vseg}{t}/{public_path}"

    thumb = join_url(th_t)
    preview = join_url(pr_t)

    def _overlay_text(value: str) -> str:
        # Keep overlay text URL-safe and ASCII-friendly for Cloudinary l_text parsing.
        ascii_value = (value or "").encode("ascii", errors="ignore").decode("ascii")
        # Keep only conservative characters for l_text payload stability.
        ascii_value = re.sub(r"[^A-Za-z0-9 _-]", " ", ascii_value)
        ascii_value = re.sub(r"\s+", " ", ascii_value).strip()
        if not ascii_value:
            ascii_value = "na"
        return ascii_value

    risk_enc = quote(_overlay_text(f"Risk: {overlay_risk}"), safe="")
    moist_enc = quote(_overlay_text(f"Moisture: {overlay_moisture}"), safe="")
    labels_text = _overlay_text(overlay_labels or "")
    if len(labels_text) > 42:
        labels_text = labels_text[:42].rstrip()
    labels_enc = quote(_overlay_text(f"Labels: {labels_text}"), safe="")
    if rt == "image":
        overlay = (
            f"https://res.cloudinary.com/{cloud}/{base_path}/{vseg}c_fill,h_480,w_800,q_auto"
            f"/l_text:Arial_32_bold:{risk_enc},g_south_west,y_20,x_20,co_rgb:2ecc71"
            f"/l_text:Arial_24:{moist_enc},g_south_west,y_64,x_20,co_rgb:ffffff"
            f"/l_text:Arial_18:{labels_enc},g_south_west,y_98,x_20,co_rgb:ffffff"
            f"/{public_path}"
        )
    else:
        # First video frame (jpg) with explainable text overlays
        overlay = (
            f"https://res.cloudinary.com/{cloud}/image/upload"
            f"/c_fill,h_480,w_800/f_jpg,so_0"
            f"/l_text:Arial_32_bold:{risk_enc},g_south_west,y_20,x_20,co_rgb:2ecc71"
            f"/l_text:Arial_24:{moist_enc},g_south_west,y_64,x_20,co_rgb:ffffff"
            f"/l_text:Arial_18:{labels_enc},g_south_west,y_98,x_20,co_rgb:ffffff"
            f"/{vseg}{public_path}"
        )

    original = f"https://res.cloudinary.com/{cloud}/{base_path}/{vseg}{public_path}"

    return TransformedMediaUrls(
        thumbnail=thumb,
        preview=preview,
        overlay=overlay,
        original_secure_url=original,
    )


def extract_cloud_name_from_url(secure_url: str | None) -> str | None:
    if not secure_url:
        return None
    p = urlparse(secure_url)
    host = p.netloc or ""
    if "res.cloudinary.com" in host and p.path.startswith("/"):
        segs = [s for s in p.path.split("/") if s]
        if segs and segs[0]:
            return segs[0]
    return None
