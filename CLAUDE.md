# Maryada: Claude Code rules (keep this file short)
Live RBI-conduct compliance coach for HUMAN loan-recovery agents. Hackathon MVP (Gnani.ai challenge), NOT an AI recovery agent, NOT production. Synthetic data only. Not legal advice.
Deadline: build finished by Nov 4 (Nov 5 buffer only), submit by Nov 9. Work in 12 phases, each on its own feature branch (docs/07). Inside a phase do not ask the user for requirements; but STOP and ask for approval before any change of scope, design or architecture (see Rules 1 and 3), and STOP after every phase.

## Session start
The SessionStart hook prints PROGRESS.md "Next step" and git state. Continue from it. `/phase N` (or `/phase rule-engine`) loads that phase's docs and branch; `/phase` alone resumes. Read only what the task needs; never read all docs.

## Stack (fixed)
Frontend: React + TypeScript + Vite + Tailwind + shadcn/ui + Zustand + Recharts (Vercel). Backend: Python 3.12, FastAPI, httpx2, websockets, Pydantic, PyYAML, stdlib sqlite3 (Docker on Render, Singapore). Gnani Prisma V3.0 STT, Timbre V3.0 TTS, gpt-5.4-mini via Euri (OpenAI-compatible, called with httpx2). Notebooks: jupytext percent `.py`.
Forbidden: ORM, Redis, Celery, LangChain, vector DB, openai SDK, socket.io, Next.js. Any new dependency needs a DECISIONS.md line.

## Commands
- Backend: `cd backend && uvicorn app.main:app --reload` | tests: `cd backend && pytest -q`
- Frontend: `cd frontend && npm run dev` | `npm run build` | `npx tsc --noEmit`
- Lint: `ruff check backend tools notebooks` | Tools: `python tools/<name>.py`
- Image: `docker build -t maryada .` | Slash commands: /phase /verify /report /progress /commit /test /review /explain

## Layout (full tree: docs/12)
`backend/app/{api,session,stt,rules,manager,security}` | `frontend/src/{pages,components,store,lib,styles}` | `content/` authored dataset (do not invent dialogue) | `notebooks/` audio | `tools/` offline scripts | `data/` shipped assets | `docs/` specs + logs.

## Rules
1. Specs are decided. Later docs override earlier ones (13 > 12 > rest). Spec silent on a small detail that changes no behaviour, UX, architecture, dependency or scope: pick the simplest option and add one line to docs/DECISIONS.md (`YYYY-MM-DD - decision - why`). Anything else is a change request (Rule 3).
2. One source of truth: dialogue/labels in `content/scenarios`, rule logic in `backend/app/rules`, numbers in `data/eval/*.json`. The frontend hard-codes none of them.
3. Follow docs/07 phase by phase. NEVER on your own: cut or skip a phase or feature, change the architecture, design, stack, API contract, rules, thresholds, voices or scope, add a dependency outside the stack, or weaken a test or acceptance criterion. If something cannot be met (failing check after 3 rounds, blocked API, schedule risk), STOP and run `/report change`: what is not working and why, what change is required, 2-3 options with impact, your recommendation. Wait for the user's approval, then log the decision in docs/DECISIONS.md and continue. The cut list (docs/00 §5) is only a menu of options to propose, never to apply unasked.
4. UI honesty: always show "Demo with synthetic calls . not legal advice . based on RBI/2026-27/223 (effective 1 Jan 2027)"; "Replay mode" badge whenever cached results are used; every wait has a visible state.
5. Save tokens: never read `.ipynb`, audio or STT caches (denied in settings); edit `notebooks/*.py` only; use `head`/`tail`/`grep` for big output; small steps; `/clear` between tasks; use agents (reviewer, debugger, test-writer) for isolated work.
6. Public files (README, docs/architecture.md, docs/conventions.md, comments, commit/PR text, .dockerignore, content/) must be professional and neutral and must NOT mention AI assistants, Claude, Anthropic or how the code was produced. Only CLAUDE.md and .claude/ may mention them.
7. Do not build ahead, do not add features, keep it boring and small.

## Testing
pytest for pure functions only (align, risk, engine, R1/R2/R4 gates, aggregate, url_guard, redact). No HTTP-mock suites. Verify the rest manually. Details: `testing` skill.

## Security
Keys come from environment variables only (`.env` is git-ignored; use `.env.example`). Never read, print, log or commit `.env` or keys; BYOK keys stay in memory, never stored or logged (docs/08). Send only synthetic transcripts to the LLM. No real phone numbers, names or recordings. No destructive commands without the user (a hook blocks them).

## Git
One feature branch per phase, named as in docs/07 (e.g. `feat/rule-engine`); never commit straight to main. Commit small via `/commit`; `/commit` runs a quick check; before a PR run `/verify` (full checks + every acceptance criterion in docs/07 + spec review). Only a passing `/verify` allows the PR and merge (a hook enforces it). After the merge STOP: run `/report phase` and wait; never start the next phase until the user says so. Branch names, commits and PR text describe the change and NEVER contain "phase", "day" or step numbers; no Co-Authored-By, "Generated with" or session links (settings and a hook enforce both). Never force-push.

## Where to look (git-ignored specs: Read by exact path; Grep/Glob skip them)
- docs/00 scope, cut list | 01 architecture, env vars, deploy | 02 API/WS events, SQLite | 03 rules engine, risk weights
- docs/05 frontend spec, never-stuck states | 06 spike and evaluation | 07 day-by-day plan | 08 Settings/BYOK
- docs/09 manager dashboard | 10 prompts, data policy, video | 11 audio notebooks, gates | 12 repo tree | 13 latency, coach voice timing
- content/README.md dataset schema | .claude/skills/ (coding, testing, debugging, documentation, audio-notebooks)
- Public docs you write: README.md, docs/architecture.md, docs/conventions.md, docs/SPIKE-RESULTS.md, docs/EVAL-NOTES.md
