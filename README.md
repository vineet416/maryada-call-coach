# Maryada

Live compliance coach for **human** loan-recovery agents. It listens to a call, colours the words that breach an RBI recovery-conduct rule, shows why and a polite alternative, speaks a short coaching nudge, and tracks a running risk score.

> Demo with synthetic calls. Not legal advice. Based on RBI/2026-27/223 (effective 1 Jan 2027). MVP, not production.

Built for Gnani.ai's Great Indian AI Internship Challenge with **Gnani Prisma V3.0** (speech-to-text) and **Gnani Timbre V3.0** (text-to-speech).

**Live site:** https://maryada.aiwithvineet.in · also at https://maryada-call-coach.vercel.app

## What you can do
- **Play a recorded run.** Replays a saved synthetic call with its flags, risk score and coach lines. No keys needed; the page is marked "Recorded".
- **Speak live.** You speak as the agent into the microphone (agent side only) for up to 3 minutes. It needs your own Gnani key and your own OpenAI-compatible language model key, entered on the Settings page.
- **Upload a recording.** Coming soon, not built.

## Evaluation results
Full engine (phrase rules plus language model check) on 30 synthetic calls with 35 labelled units, per unit, from `data/eval/eval_results.json`:

| | Clean audio |
|---|---|
| Strict precision | 75.0% (30 correct, 10 extra flags) |
| Strict recall | 85.7% (30 of 35) |
| Held-out calls (10), strict | 69.2% precision, 81.8% recall |
| Counting "needs review" as a detection | 77.8% precision, 100% recall (35 of 35) |

With phone-line noise (20, 10 and 5 dB) strict recall stays between 86% and 89%, while strict precision falls from 75% to 56%. The drop comes from rule R2 (the agent's introduction), which has no language model step: its extra advisory flags are 0 on clean audio, 1 at 20 dB, 8 at 10 dB and 15 at 5 dB.

These are synthetic calls made from text-to-speech and authored scripts, so the numbers show the method works, not how it would perform on real calls. Details and failure examples: [evaluation notes](docs/EVAL-NOTES.md).

## How this would connect to a real call centre
A real deployment would take two audio tracks from the dialer, one for the agent and one for the borrower. The engine already works on two-sided input and judges only the agent. What is not built is the dialer connection, storage, access control and a legal review of the rules. Maryada has not been run on real phone calls.

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
- No API keys are set on the server. Every live call uses the visitor's own Gnani key and their own OpenAI-compatible language model, entered on the Settings page and sent only in the request that starts the call. Recorded runs need no keys.
- `ALLOWED_ORIGINS`: the frontend URL (comma-separated for more than one). Localhost dev origins are always allowed.
- Optional (defaults in `.env.example` are fine): `MAX_LIVE_SESSIONS`, `REPLAY_ONLY`, `STT_MODE`, `PACE`, `SESSION_MAX_S`, `LLM_MODEL`, `LLM_FALLBACK_MODEL`, `LLM_HTTP2`.

Local development and the evaluation tools can use environment keys (`GNANI_API_KEY_ID`, `EURI_API_KEY`) only when `SERVER_KEYS_ENABLED=true`; it is off by default and must stay off when deployed.

Free-plan limits:
- The service sleeps after about 15 minutes idle; the first request then takes up to about a minute (the app shows a cold-start screen).
- SQLite lives inside the container, so the session log resets on every redeploy or restart.
- A monitor (for example UptimeRobot, 5-minute interval, `GET/HEAD /health`) keeps it awake; pause it when the demo period ends.

## Tests
```bash
cd backend && pip install -r requirements-dev.txt && pytest -q
```

## Architecture
A React app on Vercel talks to a FastAPI backend on Render. The backend streams each agent turn to Gnani speech-to-text, checks the text with phrase rules plus a language model the visitor brings, and returns flags, a risk score and a coach line. Read [how it works, with diagrams](docs/architecture.md) (about five minutes).

## Docs
[Architecture](docs/architecture.md) · [Evaluation notes](docs/EVAL-NOTES.md) · [Conventions](docs/conventions.md)
