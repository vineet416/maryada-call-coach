---
description: Full verification before a PR: mechanical checks + this branch's acceptance criteria + spec compliance
allowed-tools: Bash(python .claude/hooks/verify.py:*), Bash(git:*), Bash(cd:*), Bash(pytest:*), Bash(npm run:*), Bash(npx tsc:*)
---
1. Commit all work, then run `python .claude/hooks/verify.py`. It runs tests, lint, type-check, frontend build, Docker build (if backend changed), secret/size/notebook checks and the naming rules. Fix every failure and rerun until it prints VERIFY PASSED.
2. Acceptance criteria: open this branch's section in docs/07 §2. Check EACH bullet with real evidence (a command result, an event stream, a screenshot description). Write one line per criterion: PASS/FAIL + evidence.
3. Spec compliance: use the code-reviewer agent on the branch diff against the spec sections the phase cites; it must report "OK to commit".
4. Any FAIL: fix and restart at step 1 (fixes may only restore the specified behaviour, never change the design or loosen a check). After 3 failed rounds do NOT merge: log it under "Known issues" in PROGRESS.md, run `/report change`, and wait for the user. Never cut a phase or feature on your own.
5. If everything passes, put the criteria lines in the PR body under "How it was verified". Any later commit invalidates the marker: rerun.
