# Deployment

The backend runs on Render and the frontend on Vercel.

## Backend on Render
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
