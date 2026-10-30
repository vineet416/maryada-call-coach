---
description: Start or resume a build phase. /phase 3, /phase rule-engine, or /phase alone to resume from PROGRESS.md
argument-hint: [number or branch name]
---
Target = $ARGUMENTS (empty: the phase in PROGRESS.md "Next step").
1. Find the phase in docs/07 §2. Read ONLY that phase's section and the docs in its "Read before starting" column (later docs override earlier ones: 13 > 12 > rest).
2. If PROGRESS.md is missing, create it (format: docs/10 §5). Otherwise do not redo finished work; run its quick-verify commands and report pass/fail in 5 lines.
3. Create the branch from fresh main with the exact name from docs/07 (`git switch main && git pull && git switch -c <name>`), or switch to it if it exists.
4. Enter plan mode, show a plan of at most 10 lines, then execute this ONE phase only. Never cut, skip or redesign anything on your own; if blocked or over its time box, STOP and run `/report change`, then wait for the user's decision.
5. Gates G1/G2 (docs/11): never block; tell the user exactly what to listen to, keep working, use defaults if unanswered.
6. Finish: `/progress`, `/commit`, then `/verify` (mechanical checks + every acceptance criterion + spec review). Only if it fully passes: push, `gh pr create` (title and body describe the change; never mention phases, days or numbers; body includes the verification lines), `gh pr merge --squash --delete-branch`, return to updated main, set PROGRESS.md "Next step" to the next phase.
7. Then STOP. Run `/report phase` and wait. Do NOT start the next phase, create its branch, or continue building until the user explicitly runs `/phase` again. If `/verify` does not pass after 3 rounds: do not merge; run `/report change` and wait.
