---
description: Commit finished work with a clean message and no attribution lines
argument-hint: [message]
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(git add:*), Bash(git commit:*), Bash(git check-ignore:*), Bash(git log:*)
---
1. `git status -s` and `git diff --stat`. Never stage `.env*` (except .env.example), audio caches, or files over 5 MB without a reason.
1b. Run `python .claude/hooks/verify.py --quick` (tests, lint, type-check, secrets; seconds). Fix failures before committing; a commit may be a work-in-progress checkpoint but must not break tests.
2. Stage files by name (not `git add -A`).
3. Commit with message: $ARGUMENTS (if empty: one imperative line under 72 chars describing the change). Plain text only: no Co-Authored-By, no "Generated with", no links, and no words like "phase" or "day N" (a hook enforces both).
4. Print `git log -1 --oneline`.
