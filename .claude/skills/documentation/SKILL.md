---
name: documentation
description: Documentation standards for README, public docs and internal logs. Use when writing README.md, docs/*.md, PROGRESS.md or DECISIONS.md.
---
# Documentation
- **Public** (committed): `README.md`, `docs/architecture.md`, `docs/conventions.md`, `docs/SPIKE-RESULTS.md`, `docs/EVAL-NOTES.md`. Plain, short, honest; no internal planning jargon, no references to git-ignored files.
- **Private** (git-ignored): `PROGRESS.md`, `docs/DECISIONS.md`, `docs/LAUNCH.md`, planning specs `docs/NN-*.md`.
- README order: what it is (2 lines) -> demo link/GIF -> how it works -> run locally -> tests -> evaluation numbers (copied from `data/eval/eval_results.json`, never invented) -> honest limits.
- Required limits wording: synthetic calls only, not legal advice, based on RBI/2026-27/223 (effective 1 Jan 2027), MVP not production, one RBI source not primary-verified.
- DECISIONS.md line: `YYYY-MM-DD - decision - why`. PROGRESS.md format: docs/10 §5, rewritten (not appended) at the end of each work block, under 60 lines.
- Quote numbers only from measured files. No latency claim before `tools/measure_latency.py` has run.
- Tone: professional and neutral. Never mention AI assistants, Claude, Anthropic or how the project was produced in any committed file other than CLAUDE.md and .claude/, in any comment, commit message or PR.
