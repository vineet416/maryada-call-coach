# Architecture

```
Browser (React) <-- WebSocket events --> FastAPI backend --> Gnani Prisma STT (live, real-time pace)
                                              |-> rule engine: phrase prefilter + one LLM check per segment
                                              |-> SQLite session log, replay files (fallback)
Offline: notebooks (Gnani Timbre TTS) -> synthetic call audio -> evaluation harness -> eval_results.json
```

- **Frontend** (Vercel): live call screen, manager dashboard, evaluation, settings (bring-your-own keys, stored in the browser only).
- **Backend** (Docker on Render): streams pre-generated call audio to Prisma at real-time pace, runs the rules, emits events. Falls back to recorded replays on any failure.
- **Rules**: R1 calling hours, R2 identification and recording notice, R3 abuse and threats, R4 third-party disclosure, R5 false statements, R6 sensitive occasions, plus G1 good practice.
- **Checking**: per transcript segment, in two phases: an immediate phrase-match flag, then an LLM confirmation that updates it in place.
- **Data**: all calls are synthetic; no real recordings or personal data.

_Details are filled in as the system is built._
