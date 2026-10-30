#!/usr/bin/env python3
"""PreToolUse(Bash): deterministic safety. Exit 2 blocks the command and tells Claude why."""
import json, re, sys
try:
    cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
except Exception:
    sys.exit(0)

def block(msg):
    print(f"BLOCKED by guard_bash: {msg}", file=sys.stderr)
    sys.exit(2)

low = cmd.lower()
# 1. No attribution lines in commits / PRs (project rule).
if re.search(r"git\s+(commit|tag)|gh\s+pr\s+(create|edit)", low) and re.search(
        r"co-authored-by|generated with|claude\.ai/code/session|noreply@anthropic", low):
    block("commit/PR text must not contain Co-Authored-By or 'Generated with' lines. Remove them and retry.")
# 1b. No planning words in branch names, commit messages or PR text (project rule).
if re.search(r"git\s+(commit|switch\s+-c|checkout\s+-b|branch)|gh\s+pr\s+(create|edit)", low) and re.search(
        r"\bphase\b|\bday[\s_-]*\d|\bphase[\s_-]*\d|(feat|chore|fix)/p\d", low):
    block("branch/commit/PR text must describe the change; do not use 'phase', 'day' or step numbers.")
# 1c. PR create/merge only after a full verify of the current HEAD.
if re.search(r"gh\s+pr\s+(create|merge)", low):
    import os, subprocess
    root = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
        mark = open(os.path.join(root, ".claude", ".verified")).read().strip()
    except Exception:
        mark = ""
    if not head or mark != head:
        block("run /verify first (full pass on the current HEAD, with acceptance criteria checked) before opening or merging a PR.")
# 2. Never touch real env files (".env.example" is fine).
for tok in re.findall(r"[^\s'\"=:]*\.env(?:\.[\w-]+)?(?=[\s'\"]|$)", cmd):
    if not tok.endswith(".example") and not re.match(r"\s*(git check-ignore|ls|test)\b", low):
        block(f"'{tok}' holds secrets; never read, print, copy or stage it. Use environment variables.")
if re.search(r"(^|[;&|]\s*)(printenv|env|export\s+-p|set)\s*($|[;&|])", low) or \
        re.search(r"echo\s+[^|;]*\$\{?\w*(key|token|secret|password)", low):
    block("do not print environment variables or secrets.")
# 3. Destructive operations.
for m in re.finditer(r"\brm\s+(-\w*[rf]\w*\s+)+([^;&|]+)", low):
    for target in m.group(2).split():
        ok = ("node_modules" in target or "__pycache__" in target or target.rstrip("/").endswith(
            ("dist", "build", ".pytest_cache", ".ruff_cache", ".vite", "coverage")) or target.startswith("/tmp/"))
        if not ok:
            block(f"rm -rf on '{target}' needs the user's approval.")
if re.search(r"git\s+(push\s+.*(--force|-f\b)|reset\s+--hard|clean\s+-\w*f|branch\s+-D)|docker\s+system\s+prune|drop\s+(table|database)", low):
    block("destructive command; ask the user first.")
sys.exit(0)
