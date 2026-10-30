#!/usr/bin/env python3
"""SessionStart: print a compact resume brief (replaces Claude re-reading files). Never fails."""
import datetime, os, re, subprocess
root = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
t = datetime.date.today()
print(f"[Maryada] today {t} | build ends Nov 4, buffer Nov 5, submit by Nov 9 (plan: docs/07)")

def section(text, name):
    m = re.search(rf"^##+\s*{name}.*?\n(.*?)(?=^##+\s|\Z)", text, re.S | re.M | re.I)
    return m.group(1).strip() if m else ""

p = os.path.join(root, "PROGRESS.md")
if os.path.exists(p):
    txt = open(p, encoding="utf-8").read()
    for name in ("Awaiting approval", "Next step", "In progress", "Known issues", "Gate status"):
        body = section(txt, name)
        if body:
            print(f"\n## {name}\n" + "\n".join(body.splitlines()[:12]))
else:
    print("PROGRESS.md missing -> run /phase 1 (creates it).")

def git(*a):
    try:
        return subprocess.run(["git", *a], cwd=root, capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return ""
st, lg = git("status", "-s"), git("log", "-5", "--oneline")
if lg: print("\n## Recent commits\n" + lg)
if st: print("\n## Uncommitted\n" + "\n".join(st.splitlines()[:15]))
