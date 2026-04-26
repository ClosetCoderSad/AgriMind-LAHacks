# Cloudinary webhook + ASI:One demo

This documents the **event-driven media pipeline** added for AgriMind: Cloudinary upload notifications hit `POST /api/cloudinary/webhook`, the backend verifies signatures, runs **TwelveLabs video intelligence** + **sustainability-style outputs**, generates **Cloudinary transformation URLs** (thumbnail, preview, overlay), and stores the result for ASI:One.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/cloudinary/webhook` | Cloudinary `notification_url` target (raw body + `X-Cld-*` headers) |
| GET | `/api/cloudinary/latest` | Latest stored webhook result (for demos + Agentverse tool) |
| GET | `/api/cloudinary/events?limit=20` | Recent events |

## Environment variables

| Variable | Purpose |
|----------|---------|
| `CLOUDINARY_CLOUD_NAME` | Cloud name (also used for `res.cloudinary.com` URLs) |
| `CLOUDINARY_API_SECRET` | Required for **production** webhook verification |
| `CLOUDINARY_WEBHOOK_SKIP_VERIFY` | Set `true` only for local/ngrok testing without signing |
| `CLOUDINARY_WEBHOOK_MAX_AGE_SEC` | Max age of `X-Cld-Timestamp` (default 7200) |
| `CLOUDINARY_12L_SUMMARY_RETRIES` / `CLOUDINARY_12L_SUMMARY_WAIT_SEC` | Short retry window after ingest so summarize can succeed |
| `TWELVELABS_*` | Same as before; video path uses `secure_url` for indexing |
| `AGRIMIND_API_BASE` | Base URL of this FastAPI app (or public tunnel) for `agri.cloudinary_latest` in the **orchestrator agent** |

## Cloudinary console setup (short)

1. Upload a **video** to a folder e.g. `farms/plot_a/` with **tags** and optional **context** for progression (`plant_id`, `day_index`, etc. if you use them as custom context fields in your uploader).
2. Set a **Notification URL** (upload preset or account webhook) to your public URL: `https://<host>/api/cloudinary/webhook`.
3. In production, **disable** `CLOUDINARY_WEBHOOK_SKIP_VERIFY` and set `CLOUDINARY_API_SECRET`.

## ASI:One (Fetch.ai) demo flow

1. Expose the API (or deploy) so Cloudinary and Agentverse can reach it.
2. Set `AGRIMIND_API_BASE` in the process that runs the orchestrator to that public base URL.
3. Upload a plant clip to Cloudinary so the webhook fires and populates `cloudinary_event_log` via `/api/cloudinary/webhook`.
4. In **ASI:One**, send JSON: `{"tool":"agri.cloudinary_latest","args":{}}`  
   The reply includes the latest `result` with `transformed_media_urls`, `sustainability`, and TwelveLabs `video_id` when enabled.

## Track fit (submission bullets)

- **Fetch.ai / ASI:One** — End-to-end intent: upload → event → tool execution (TwelveLabs + irrigation/sustainability bundle) → explainable result JSON for chat.
- **Cloudinary** — Real **notification signatures**, **on-the-fly transformation URLs** (thumbnails, overlay explainability on image / first video frame), **video delivery** as the media engine.
- **Sustain the Spark** — `sustainability` in the result ties visual crop stress to water/fertilizer narrative; position as reducing waste through earlier visual disease detection and smarter irrigation.

## Smoke test (local, skip verify)

1. `CLOUDINARY_WEBHOOK_SKIP_VERIFY=true`
2. `POST /api/cloudinary/webhook` with a small JSON or form body that includes at least `public_id`, `resource_type`, `secure_url` (and `version` if applicable).
3. `GET /api/cloudinary/latest` and confirm a stored `result`.
