"""Build data/eval/manager_data.json for the Manager page from saved evaluation results (no network, no model).

Reads the clean-audio results of the full engine when it has a complete set, otherwise the rules-only baseline, plus
content/agents.yaml and content/scenarios/. Uses what the engine detected, never the labels. Per-call risk is computed
with the engine's own risk meter (backend/app/rules/risk.py) over the agent turns in order.

  backend/.venv/Scripts/python.exe tools/build_manager_data.py
"""
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import yaml
from app.manager.aggregate import aggregate
from app.rules import risk
from app.rules.schemas import Finding

EVAL = ROOT / "data" / "eval"
CONDITION = "clean"
SOURCES = {
    "full": "These numbers are what Maryada's engine (phrase checks and a language model) detected on the 30 synthetic calls, played on clean audio, grouped by the fictional agent persona each call is assigned to. They are not real agents and not the dataset labels.",
    "rules_only": "These numbers are what Maryada's phrase checks alone detected on the 30 synthetic calls on clean audio (the language model was not run), grouped by the fictional agent persona each call is assigned to. They are not real agents and not the dataset labels.",
}


def call_risk(turns: list[dict], detections: list[dict]) -> tuple[int, list[int]]:
    """Peak risk and the score after each agent turn: risk.update per agent turn, in order, as in a live call."""
    score, peak, trace = 0, 0, []
    for t in turns:
        if t["speaker"] != "A":
            continue
        fs = [Finding(rule_id=d["rule"], kind=d["kind"], confidence=d["confidence"], turn_idx=d["turn"], quote=d["quote"])
              for d in detections if d["turn"] == t["idx"]]
        score = risk.update(score, fs).score
        peak = max(peak, score)
        trace.append(score)
    return peak, trace


def build_call(sc: dict, run: dict) -> dict:
    """One call row. Findings are the engine's detections, one per (turn, rule) with the strongest kind first."""
    rank = {"violation": 3, "advisory": 2, "needs_review": 1, "good_practice": 0}
    best: dict[tuple[int, str], dict] = {}
    for d in run["detections"]:
        k = (d["turn"], d["rule"])
        if k not in best or rank[d["kind"]] > rank[best[k]["kind"]]:
            best[k] = d
    findings = [{"rule_id": d["rule"], "kind": d["kind"], "turn_idx": d["turn"], "quote": d["quote"]}
                for d in sorted(best.values(), key=lambda d: (d["turn"], d["rule"]))]
    peak, trace = call_risk(run["turns"], run["detections"])
    hh = sc["time"].split(":")[0]
    return {"call_id": sc["id"], "title": sc["title"], "agent_id": sc["agent"], "call_date": sc["date"],
            "call_time": sc["time"], "hour": int(hh), "risk_peak": peak, "risk_by_turn": trace, "findings": findings}


def pick_source() -> tuple[str, Path]:
    """The full engine if its clean results are complete, else the rules-only baseline; error if neither."""
    results = json.loads((EVAL / "eval_results.json").read_text(encoding="utf-8"))
    for mode, key in (("full", "full"), ("rules_only", "ablation_llm_off")):
        block = (results.get(key) or {}).get(CONDITION)
        if block and block.get("complete"):
            return mode, EVAL / "runs" / mode / CONDITION
    raise SystemExit("No complete clean-audio evaluation results: run tools/run_eval.py first.")


def main() -> int:
    mode, folder = pick_source()
    agents = yaml.safe_load((ROOT / "content" / "agents.yaml").read_text(encoding="utf-8"))["agents"]
    roster = [{"id": a["id"], "name": a["name"], "team": a["team"]} for a in agents]
    scenarios = []
    for f in sorted((ROOT / "content" / "scenarios").glob("*.yaml")):
        scenarios += yaml.safe_load(f.read_text(encoding="utf-8"))["scenarios"]
    calls = []
    for sc in scenarios:
        run = json.loads((folder / f"{sc['id']}.json").read_text(encoding="utf-8"))
        if run["mode"] != mode or run["condition"] != CONDITION:
            raise SystemExit(f"{sc['id']}: result file is not {mode}/{CONDITION}")
        calls.append(build_call(sc, run))
    agg = aggregate(calls, roster)
    out = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "batch_label": f"{len(calls)} synthetic calls, {len(roster)} fictional agents, clean audio",
        "source": {"mode": mode, "condition": CONDITION, "note": SOURCES[mode]},
        "n_calls": len(calls), "roster": roster, "calls": calls,
        "agents": agg["agents"], "by_day": agg["by_day"], "by_hour": agg["by_hour"], "rule_totals": agg["rule_totals"],
    }
    path = EVAL / "manager_data.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}: {len(calls)} calls from {mode}/{CONDITION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
