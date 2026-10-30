#!/usr/bin/env python3
"""PostToolUse(Edit|Write): cheap format + syntax validation of the ONE edited file. Never runs tests."""
import json, os, shutil, subprocess, sys
try:
    path = json.load(sys.stdin).get("tool_input", {}).get("file_path", "")
except Exception:
    sys.exit(0)
if not path or not os.path.isfile(path):
    sys.exit(0)
root = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
ext = os.path.splitext(path)[1].lower()

def run(*a):
    try:
        return subprocess.run(a, capture_output=True, text=True, timeout=20)
    except Exception:
        return None

def fail(msg):
    print(msg[:800], file=sys.stderr)
    sys.exit(2)

if ext == ".py" and shutil.which("ruff"):
    run("ruff", "format", "-q", path)
    r = run("ruff", "check", "--fix", "-q", path)
    if r and r.returncode not in (0, None) and r.stdout.strip():
        fail("ruff: " + r.stdout)
elif ext in (".ts", ".tsx", ".css", ".json") and "/frontend/" in path.replace("\\", "/") \
        and "package-lock" not in path:
    prettier = os.path.join(root, "frontend", "node_modules", ".bin", "prettier")
    if os.path.exists(prettier):
        run(prettier, "--write", path)
if ext == ".json":
    try: json.load(open(path, encoding="utf-8"))
    except Exception as e: fail(f"Invalid JSON in {path}: {e}")
if ext in (".yaml", ".yml"):
    try:
        import yaml
        yaml.safe_load(open(path, encoding="utf-8"))
    except ImportError:
        pass
    except Exception as e:
        fail(f"Invalid YAML in {path}: {e}")
sys.exit(0)
