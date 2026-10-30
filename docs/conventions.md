# Conventions
- Python 3.12 with type hints; Pydantic models for all events. Rule logic is pure functions, tested with pytest.
- TypeScript strict; colours and fonts only from `styles/tokens.css`.
- One source of truth: dialogue in `content/`, rules in `backend/app/rules`, numbers in `data/eval/`.
- Secrets only via environment variables; `.env` is never committed.
- Commits: short imperative line, plain text.
