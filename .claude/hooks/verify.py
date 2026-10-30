#!/usr/bin/env python3
"""Mechanical pre-PR verification. `verify.py --quick` (before commits) or `verify.py` (full, before PR/merge).
A full pass writes .claude/.verified = HEAD sha; guard_bash blocks `gh pr create/merge` without it."""
import glob, json, os, re, shutil, subprocess, sys
root = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()); os.chdir(root)
quick = "--quick" in sys.argv
fails, notes = [], []

def run(cmd, cwd=".", timeout=600):
    try:
        cmd = [shutil.which(cmd[0]) or cmd[0], *cmd[1:]]  # Windows: resolve npx.cmd / npm.cmd
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:
        return 1, str(e)

def step(name, cmd, cwd="."):
    rc, out = run(cmd, cwd)
    print(f"[{'ok' if rc == 0 else 'FAIL'}] {name}")
    if rc != 0:
        fails.append(name); print("\n".join(out.splitlines()[-15:]))

def git(*a): return run(["git", *a])[1]

branch = git("rev-parse", "--abbrev-ref", "HEAD")
if branch in ("main", "master") and not quick:
    fails.append("on main: work must be on a feature branch")
bad = re.compile(r"\bphase\b|\bday[\s_-]*\d|\bphase[\s_-]*\d|(feat|chore|fix)/p\d", re.I)
base = "main" if run(["git", "rev-parse", "--verify", "main"])[0] == 0 else "HEAD~20"
subjects = git("log", f"{base}..HEAD", "--format=%s%n%b")
if bad.search(branch) or bad.search(subjects):
    fails.append("branch name or commit text contains 'phase'/'day N'")
if re.search(r"co-authored-by|generated with", subjects, re.I):
    fails.append("commit text contains an attribution line")

if os.path.isdir("backend/tests") and glob.glob("backend/tests/test_*.py"):
    step("pytest", [sys.executable, "-m", "pytest", "-q", "-x"], "backend")
if shutil.which("ruff"):
    dirs = [d for d in ("backend", "tools", "notebooks") if os.path.isdir(d)]
    if dirs: step("ruff", ["ruff", "check", *dirs])
if os.path.exists("frontend/package.json") and os.path.isdir("frontend/node_modules"):
    step("tsc", ["npx", "tsc", "--noEmit"], "frontend")
    if not quick: step("frontend build", ["npm", "run", "build"], "frontend")
if not quick and os.path.exists("Dockerfile") and shutil.which("docker") and \
        git("diff", "--name-only", f"{base}..HEAD").find("backend/") >= 0:
    step("docker build", ["docker", "build", "-q", "-t", "maryada-verify", "."])

# secrets / size / notebook hygiene on everything this branch changes
changed = [f for f in git("diff", "--name-only", f"{base}..HEAD").splitlines() if os.path.isfile(f)]
pat = re.compile(r"sk-[A-Za-z0-9]{20,}|(GNANI_API_KEY_ID|EURI_API_KEY)\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{12,}")
ai_mention = re.compile(r"\bclaude\b|anthropic|ai[- ]generated|generated (by|with) ai", re.I)
for f in changed:
    if os.path.basename(f).startswith(".env") and not f.endswith(".example"):
        fails.append(f"secret file committed: {f}")
    if os.path.getsize(f) > 5_000_000: notes.append(f"large file (>5MB): {f}")
    pub = f.replace("\\", "/")
    exempt = pub == "CLAUDE.md" or pub.startswith(".claude/") or pub == ".gitignore" or pub.endswith((".lock", "lock.json"))
    if not exempt and (f.endswith((".md", ".py", ".ts", ".tsx", ".json", ".yaml", ".yml", ".ipynb", ".example"))
                       or os.path.basename(f) == ".dockerignore"):
        try:
            if ai_mention.search(open(f, encoding="utf-8", errors="ignore").read()):
                fails.append(f"public file mentions an AI assistant (remove it): {f}")
        except Exception: pass
    if f.endswith((".md", ".py", ".ts", ".tsx", ".json", ".yaml", ".yml", ".ipynb", ".example")):
        try:
            if pat.search(open(f, encoding="utf-8", errors="ignore").read()):
                fails.append(f"possible key in {f}")
        except Exception: pass
    if f.endswith(".ipynb"):
        try:
            nb = json.load(open(f, encoding="utf-8"))
            if any(c.get("outputs") for c in nb.get("cells", [])): fails.append(f"notebook has outputs: {f}")
        except Exception: pass

if not quick:
    if git("status", "--porcelain", "--untracked-files=no"):
        fails.append("uncommitted tracked changes: commit first")
if fails:
    print("\nVERIFY FAILED:\n- " + "\n- ".join(fails)); sys.exit(1)
for n in notes: print("note:", n)
if not quick:
    open(os.path.join(".claude", ".verified"), "w").write(git("rev-parse", "HEAD"))
    print("\nVERIFY PASSED (full). Marker written for", git("rev-parse", "--short", "HEAD"))
else:
    print("\nQUICK CHECK PASSED")
