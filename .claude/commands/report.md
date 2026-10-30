---
description: Write a report for the user and stop. /report phase (after a merged phase) or /report change (blocked or a change is needed)
argument-hint: phase | change
---
Write the report in the chat (max 25 lines, plain language, no code dumps), copy the key lines to PROGRESS.md under "Awaiting approval", then STOP and wait. Do not continue building.

**/report phase** (a phase is merged):
1. Delivered: what now works, branch and PR title.
2. Verified: the acceptance lines (PASS + evidence) and any check that could not run.
3. Needs the user: anything to listen to, approve or set up (gates G1/G2, Render, UptimeRobot, keys).
4. Deviations: every DECISIONS.md line added in this phase.
5. Next: the next phase's name and what `/phase` command to run. Ask the user to say go.

**/report change** (something fails, is blocked, or a spec must change):
1. What is not working, with evidence (command, error, measurement).
2. Why (root cause, or best hypothesis marked as such).
3. Change required: exactly which spec, design, scope or dependency would change.
4. Options (2-3), each with effect on features, quality and schedule.
5. Recommendation and why.
6. Decision needed: the exact question the user must answer.
After the user decides, log it in docs/DECISIONS.md, then continue.
