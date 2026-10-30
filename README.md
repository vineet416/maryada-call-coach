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

## Tests
```bash
cd backend && pip install -r requirements-dev.txt && pytest -q
```

## Docs
[Architecture](docs/architecture.md) · [Conventions](docs/conventions.md)
