---
description: Run backend tests (and frontend type-check if frontend changed); summarise
allowed-tools: Bash(pytest:*), Bash(cd:*), Bash(npx tsc:*), Bash(git status:*)
---
1. `cd backend && pytest -q -x` 
2. If `git status -s` shows frontend/ changes: `cd frontend && npx tsc --noEmit`.
Report in at most 8 lines: pass/fail counts and the first failure. On failure, hand the symptom to the debugger agent; do not paste full output.
