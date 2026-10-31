# Maryada

Live compliance coach for **human** loan-recovery agents. It listens to a call, colours the words that breach an RBI recovery-conduct rule, shows why and a polite alternative, speaks a short coaching nudge, and tracks a running risk score.

> Demo with synthetic calls. Not legal advice. Based on RBI/2026-27/223 (effective 1 Jan 2027). MVP, not production.

Built for Gnani.ai's Great Indian AI Internship Challenge with **Gnani Prisma V3.0** (speech-to-text) and **Gnani Timbre V3.0** (text-to-speech).

_Demo link, GIF and evaluation numbers: added at launch._

## Run locally
Requirements: Python 3.12+, Node 20+, ffmpeg (audio tools only).
```bash
cp .env.example .env          # fill GNANI_API_KEY_ID and EURI_API_KEY
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload
cd frontend && npm install && npm run dev
```

## Deployment (backend on Render)
One Docker web service, region Singapore, built from the root `Dockerfile` (no build or start command; it listens on `$PORT`). Health check path: `/health`.

Environment variables (set in the Render Environment tab):
- Secrets: `GNANI_API_KEY_ID`, `EURI_API_KEY`.
- `ALLOWED_ORIGINS`: the frontend URL (comma-separated for more than one). Localhost dev origins are always allowed.
- Optional (defaults in `.env.example` are fine): `DAILY_SESSION_CAP`, `REPLAY_ONLY`, `STT_MODE`, `PACE`, `SESSION_MAX_S`, `LLM_MODEL`, `LLM_FALLBACK_MODEL`, `LLM_HTTP2`. Without both keys the service starts in replay-only mode.

Free-plan limits:
- The service sleeps after about 15 minutes idle; the first request then takes up to about a minute (the app shows a cold-start screen).
- SQLite lives inside the container, so the daily counter and session log reset on every redeploy or restart.
- A monitor (for example UptimeRobot, 5-minute interval, `GET/HEAD /health`) keeps it awake; pause it when the demo period ends.

## Tests
```bash
cd backend && pip install -r requirements-dev.txt && pytest -q
```

## Docs
[Architecture](docs/architecture.md) · [Conventions](docs/conventions.md)
