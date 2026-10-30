---
name: debugging
description: Maryada debugging workflow for streaming, STT, LLM and UI problems. Use when something fails, is slow, or behaves unexpectedly.
---
# Debugging
1. Reproduce with the smallest case (one scenario, `PACE` high if timing is irrelevant). Write down the exact symptom.
2. Read the last 30 log lines only (`tail -n 30`), filtered by `session_id`; never dump whole logs.
3. Locate the layer: audio file -> Prisma socket -> `transcript.final` -> prefilter -> LLM -> `finding.*` event -> store -> component. Check the event stream first, then the UI.
4. Form 1-3 hypotheses, test the cheapest first. Check `docs/SPIKE-RESULTS.md` for real API formats before suspecting the API.
5. Fix the root cause with the smallest diff; add a pytest case if it is a pure function.
6. Slowness: use the `latency` fields on events (docs/13 §5) before guessing.
7. Still stuck after 3 attempts: record the finding under "Known issues" in PROGRESS.md and fall back (replay / prefilter-only) rather than burning the day.
Never print keys or `.env`; never "fix" by silencing an error.
