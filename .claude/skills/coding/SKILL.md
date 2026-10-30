---
name: coding
description: Maryada coding conventions for backend (FastAPI/Python) and frontend (React/TS). Use when writing or changing application code.
---
# Coding
**Backend**
- Python 3.12, type hints everywhere, Pydantic models for every event/request (shapes: docs/02). Async I/O only; reuse the one shared `httpx2.AsyncClient`.
- Rule logic = pure functions in `backend/app/rules/` (no I/O) so they are testable; I/O lives in `stt/`, `session/`, `api/`.
- Never hard-code keys, URLs of user LLMs, or rule text; read config from `config.py` and rules from `content/rules.yaml`.
- Errors: catch at the boundary, emit a user-visible state (never silent, never stuck: docs/05 §6); log with `session_id`, `turn_idx`; never log keys or transcripts of BYOK users.
- Keep functions short; no dead code, no speculative abstractions, no new dependency without a DECISIONS.md line.

**Frontend**
- Function components, TypeScript strict, Zustand for state, colours/fonts only from `styles/tokens.css`.
- Memoise transcript bubbles; batch event updates; paint flags immediately (docs/13 §4.7).
- The UI never hard-codes rule text or eval numbers: they come from the API.
- Every async view has loading, empty and error states; 390 px width must work.

Comments: only for non-obvious "why". Match existing naming in docs/12.
