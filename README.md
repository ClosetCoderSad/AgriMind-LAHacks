# AgriMind (LA Hacks 2026)

AgriMind is a React + FastAPI + Fetch.ai multi-agent farming platform with Cloudinary media ingestion and TwelveLabs video intelligence.

This README is the full local runbook: what to put in env files, what to run in each terminal, and how to expose the backend with ngrok for webhooks/agent demos.

## 1) Prerequisites

- Node.js (see `engines` in `package.json`; Node 20+ recommended)
- Python 3.10+ (3.11 recommended)
- `pip`
- ngrok (optional, required for public webhook/tunnel demos)

## 2) Install dependencies

From repo root:

```powershell
cd C:\Users\ahnaf\Downloads\farm-master\farm-master
npm install
```

Create + activate Python venv, then install backend deps:

```powershell
python -m venv .regenv
.\.regenv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

If you run the classifier API separately, also install:

```powershell
pip install torch torchvision pillow fastapi uvicorn python-multipart
```

## 3) Environment variables (API keys + config)

Do not commit secrets. Keep real values only in local `.env` files.

### Frontend env (`.env` at repo root)

Used by React/Vite:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_CLOUDINARY_CLOUD_NAME=your_cloud_name
VITE_CLOUDINARY_UPLOAD_PRESET=your_unsigned_upload_preset
VITE_CLASSIFIER_API_URL=http://127.0.0.1:8010

# Optional Auth0
VITE_AUTH0_DOMAIN=
VITE_AUTH0_CLIENT_ID=
```

### Backend env (`backend/.env`)

Used by FastAPI + agents:

```env
# Core backend
CORS_ORIGIN=http://localhost:5173
SQLITE_PATH=backend/storage/agrimind.db

# Cloudinary
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_cloudinary_api_key
CLOUDINARY_API_SECRET=your_cloudinary_api_secret
CLOUDINARY_INGEST_UPLOAD_PRESET=your_unsigned_upload_preset
CLOUDINARY_WEBHOOK_SKIP_VERIFY=false
CLOUDINARY_WEBHOOK_MAX_AGE_SEC=7200

# TwelveLabs
TWELVELABS_ENABLED=true
TWELVELABS_API_KEY=your_twelvelabs_api_key
TWELVELABS_INDEX_ID=your_twelvelabs_index_id
TWELVELABS_POLL_INTERVAL_SEC=5
TWELVELABS_MAX_POLL_ATTEMPTS=30

# Agent + public API base for orchestrator tools
AGRIMIND_API_BASE=http://127.0.0.1:8000
ORCHESTRATOR_SEED_PHRASE=replace_with_unique_random_string
ORCHESTRATOR_PORT=8010
HEALTH_SEED_PHRASE=replace_with_unique_random_string
HEALTH_AGENT_PORT=8011
IRRIGATION_SEED_PHRASE=replace_with_unique_random_string
IRRIGATION_AGENT_PORT=8012
SUSTAINABILITY_SEED_PHRASE=replace_with_unique_random_string
SUSTAINABILITY_AGENT_PORT=8013
ENABLE_MAILBOX=true
PUBLISH_AGENT_DETAILS=true

# Optional local Gemma-style explanation endpoint
GEMMA_API_URL=
GEMMA_API_KEY=
```

## 4) Terminal-by-terminal startup (recommended)

Open all terminals in:

`C:\Users\ahnaf\Downloads\farm-master\farm-master`

### Terminal 1 - Frontend (Vite)

```powershell
npm run dev
```

Expected: frontend at `http://localhost:5173`

### Terminal 2 - Backend API (FastAPI main.py)

Preferred explicit command:

```powershell
python -m uvicorn backend.app.main:app --app-dir "C:\Users\ahnaf\Downloads\farm-master\farm-master" --host 127.0.0.1 --port 8000 --reload
```

Equivalent npm script:

```powershell
npm run dev:backend
```

Expected: API at `http://127.0.0.1:8000` and health at `/api/health`

### Terminal 3 - Orchestrator agent (orchestrator.py)

Use module mode (import-safe):

```powershell
python -m backend.agents.orchestrator_agent
```

### Terminal 4 - ngrok tunnel (optional but recommended for demos)

```powershell
ngrok http 8000
```

Copy the generated HTTPS forwarding URL (example: `https://xxxx.ngrok-free.app`).

Then update:

- root `.env`: `VITE_API_BASE_URL=https://xxxx.ngrok-free.app` (if frontend should call tunneled backend)
- `backend/.env`: `AGRIMIND_API_BASE=https://xxxx.ngrok-free.app` (for orchestrator Cloudinary tools)
- Cloudinary notification URL: `https://xxxx.ngrok-free.app/api/cloudinary/webhook`

Restart frontend/backend/agent after env changes.

### Optional terminals - Other agents

```powershell
python -m backend.agents.health_agent
python -m backend.agents.irrigation_agent
python -m backend.agents.sustainability_agent
```

### Optional terminal - Classifier service

```powershell
python classification-model\leaf_disease_classifier.py --serve --host 127.0.0.1 --port 8010
```

If running this, keep `VITE_CLASSIFIER_API_URL=http://127.0.0.1:8010`.

## 5) Sanity checks after startup

- Frontend loads at `http://localhost:5173`
- Backend health works:

```powershell
curl http://127.0.0.1:8000/api/health
```

- TwelveLabs page can:
  - ingest a public video URL
  - load index videos
  - run summary + Q&A
- Cloudinary upload works and `/api/cloudinary/latest` returns data after webhook events

## 6) ASI:One / Fetch.ai tool-call notes

Orchestrator supports these tool names:

- `twelvelabs.ingest_video`
- `twelvelabs.summarize_video`
- `twelvelabs.ask_video`
- `twelvelabs.analyze_video`
- `agri.cloudinary_latest`
- `agri.cloudinary_analyze_uri`

Payload shape:

```json
{
  "tool": "twelvelabs.analyze_video",
  "args": {
    "video_id": "your_video_id"
  }
}
```

## 7) Common issues

- **Import errors when starting orchestrator**: run `python -m backend.agents.orchestrator_agent` (not file path execution).
- **CORS blocked in browser**: set `CORS_ORIGIN` to your frontend origin and restart backend.
- **Cloudinary webhook 403**: verify `CLOUDINARY_API_SECRET`; use `CLOUDINARY_WEBHOOK_SKIP_VERIFY=true` only for local debugging.
- **No TwelveLabs output**: verify `TWELVELABS_ENABLED=true`, valid `TWELVELABS_API_KEY`, and correct `TWELVELABS_INDEX_ID`.
- **Agent can’t fetch latest Cloudinary event**: ensure `AGRIMIND_API_BASE` points to reachable backend URL.

## 8) Reference docs

- Cloudinary webhook + submissions: [docs/CLOUDINARY_WEBHOOK_AND_SUBMISSIONS.md](docs/CLOUDINARY_WEBHOOK_AND_SUBMISSIONS.md)
- Cloudinary React SDK: [cloudinary.com/documentation/react_integration](https://cloudinary.com/documentation/react_integration)
- Vite docs: [vite.dev](https://vite.dev)

