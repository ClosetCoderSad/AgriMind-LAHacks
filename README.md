# farm

A Cloudinary React + Vite + TypeScript project scaffolded with [create-cloudinary-react](https://github.com/cloudinary-devs/create-cloudinary-react).

## Prerequisites

- **Node.js** — use a current LTS release. Supported ranges are listed under `engines` in this `package.json`.

## Quick Start

```bash
npm run dev
```

## Backend + Agent Setup (Phase 1)

AgriMind now includes a Python backend in `backend/` with FastAPI endpoints and Fetch.ai-compatible agent files.

1. Create and activate a Python virtual environment.
2. Install backend dependencies:

```bash
pip install -r backend/requirements.txt
```

3. Copy env template and fill seed phrases:

```bash
copy backend/.env.example backend/.env
```

4. Start backend API:

```bash
npm run dev:backend
```

5. Start frontend:

```bash
npm run dev
```

6. Optional: run agents in separate terminals:

```bash
npm run agent:orchestrator
npm run agent:health
npm run agent:irrigation
npm run agent:sustainability
```

Set `VITE_API_BASE_URL` in your frontend `.env` if your backend does not run on `http://localhost:8000`.

## Cloudinary Setup

This project uses Cloudinary for image management. If you don't have a Cloudinary account yet:

- [Sign up for free](https://cld.media/reactregister)
- Find your cloud name in your [dashboard](https://console.cloudinary.com/app/home/dashboard)

## Environment Variables

Your `.env` file has been pre-configured with:

- `VITE_CLOUDINARY_CLOUD_NAME`: dafeglj6d
- `VITE_CLOUDINARY_UPLOAD_PRESET`: y

**Note**: Transformations work without an upload preset (using sample images). Uploads require an unsigned upload preset.

To create an unsigned upload preset:

1. Go to https://console.cloudinary.com/app/settings/upload/presets
2. Click "Add upload preset"
3. Set it to "Unsigned" mode
4. Add the preset name to your `.env` file
5. **Save** the `.env` file and restart the dev server so the new values load correctly.

### Webhook + event-driven analysis (AgriMind backend)

- Point Cloudinary’s **Notification URL** (or upload preset) at `POST /api/cloudinary/webhook` on your public API base.
- Set `CLOUDINARY_API_SECRET` and keep `CLOUDINARY_WEBHOOK_SKIP_VERIFY=false` in production; use skip-verify only for local tests.
- For **ASI:One**, the orchestrator tool `agri.cloudinary_latest` calls `GET /api/cloudinary/latest` — set `AGRIMIND_API_BASE` to your API URL in the agent environment.
- Full steps and submission notes: [docs/CLOUDINARY_WEBHOOK_AND_SUBMISSIONS.md](docs/CLOUDINARY_WEBHOOK_AND_SUBMISSIONS.md)

## AI Assistant Support

This project includes AI coding rules for your selected AI assistant(s). The rules help AI assistants understand Cloudinary React SDK patterns, common errors, and best practices.

**Try the AI Prompts**: Check out the "🤖 Try Asking Your AI Assistant" section in the app for ready-to-use Cloudinary prompts! Copy and paste them into your AI assistant to get started.

## Learn More

- [Cloudinary React SDK Docs](https://cloudinary.com/documentation/react_integration)
- [Vite Documentation](https://vite.dev)
- [React Documentation](https://react.dev)
