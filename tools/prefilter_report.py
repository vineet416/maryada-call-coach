"""Report: prefilter + gates (no LLM, no HTTP) against the labels in content/scenarios/*.yaml.

Prints expected vs detected per call and per rule, with false positives and misses.
Report only: it never edits scripts, labels, phrases, thresholds or weights.
Usage: backend/.venv/Scripts/python.exe tools/prefilter_report.py
"""
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.rules.engine import fast_findings
from app.rules.schemas import CallContext, Turn

RULES = ["R1", "R2", "R3", "R4", "R5", "R6"]
CLEAN = {"c01", "c02", "c03", "c04", "c05", "c18", "c27", "c30"}


def load_calls() -> list[dict]:
    calls = []
    for p in sorted((ROOT / "content" / "scenarios").glob("*.yaml")):
        calls += yaml.safe_load(p.read_text(encoding="utf-8"))["scenarios"]
    return sorted(calls, key=lambda c: int(c["id"][1:]))


def run_call(sc: dict) -> tuple[set, set, dict]:
    """Return (expected {(turn, rule)}, detected {(turn, rule)}, kinds {(turn, rule): kind})."""
    ctx = CallContext(answered_by=sc["answered_by"], simulated_start_time=sc["time"])
    exp, det, kinds, hist = set(), set(), {}, []
    for i, t in enumerate(sc["turns"], 1):
        for rule, _ in t.get("L", []) or []:
            exp.add((i, rule))
        if t["s"] == "A":
            for f in fast_findings(ctx, hist, i, t["t"]):
                if f.kind != "good_practice":
                    det.add((i, f.rule_id))
                    kinds[(i, f.rule_id)] = f.kind
        hist.append(Turn(speaker=t["s"], text=t["t"]))
    return exp, det, kinds


def fmt(items: set) -> str:
    return " ".join(f"t{t}:{r}" for t, r in sorted(items)) or "-"


def main() -> None:
    per_rule = defaultdict(lambda: {"tp": 0, "fp": 0, "miss": 0})
    mismatches, rows = [], []
    for sc in load_calls():
        exp, det, kinds = run_call(sc)
        fp, miss = det - exp, exp - det
        for _, r in exp & det:
            per_rule[r]["tp"] += 1
        for _, r in fp:
            per_rule[r]["fp"] += 1
        for _, r in miss:
            per_rule[r]["miss"] += 1
        flag = "ok" if not fp and not miss else "MISMATCH"
        tag = "clean/HN" if sc["id"] in CLEAN else ("hard-neg" if sc.get("hard_negative") else "")
        rows.append((sc["id"], sc["answered_by"], sc["time"], tag, fmt(exp), fmt(det), fmt(fp), fmt(miss), flag))
        if fp or miss:
            mismatches.append((sc["id"], fp, miss, kinds))
    head = ("call", "answered", "time", "type", "expected", "detected", "false_pos", "missed", "result")
    widths = [max(len(str(r[i])) for r in [head, *rows]) for i in range(len(head))]
    for r in [head, *rows]:
        print("  ".join(str(c).ljust(w) for c, w in zip(r, widths)))
    print("\nPer rule (turn-level, detection per call/turn/rule):")
    print("rule  expected  detected  TP  FP  miss")
    for r in RULES:
        d = per_rule[r]
        print(f"{r:<5} {d['tp'] + d['miss']:<9} {d['tp'] + d['fp']:<9} {d['tp']:<3} {d['fp']:<3} {d['miss']}")
    print("\nChecks requested:")
    by = {r[0]: r for r in rows}
    clean_bad = [c for c in sorted(CLEAN) if by[c][5] != "-"]
    print(f"- clean/hard-negative calls with any finding: {clean_bad or 'none'}")
    for grp, rule in (("c19-c24,c28", "R1/R2"), ("c15-c17,c29", "R4")):
        ids = [f"c{n}" for n in (19, 20, 21, 22, 23, 24, 28)] if rule == "R1/R2" else ["c15", "c16", "c17", "c29"]
        print(f"- {rule} on {grp}: " + ", ".join(f"{c}={by[c][8]}" for c in ids))
    print(f"- R4 on c18 (answered_by {by['c18'][1]}): detected {by['c18'][5]}")
    print(f"\n{len(mismatches)} call(s) with mismatches:")
    for cid, fp, miss, kinds in mismatches:
        print(f"  {cid}: false positives [{fmt(fp)}] kinds {[kinds[x] for x in sorted(fp)]}; misses [{fmt(miss)}]")


if __name__ == "__main__":
    main()
