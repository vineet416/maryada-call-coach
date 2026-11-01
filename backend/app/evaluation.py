"""Evaluation page data: the committed results file and the time-to-flag statistics from the committed recordings.

Nothing is computed from the evaluation results here and no model or speech service is called; the numbers in
eval_results.json are written by tools/run_eval.py and passed on unchanged.
"""
import json
import math
from pathlib import Path

from .config import settings

PHASES = (("fast", "Fast phrase check"), ("deep", "Deep language check"))


def percentile(values: list[float], q: float) -> float | None:
    """Linear interpolation between ranks (q in 0..100). None for an empty list."""
    if not values:
        return None
    xs = sorted(values)
    pos = (len(xs) - 1) * q / 100
    lo, hi = math.floor(pos), math.ceil(pos)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def _row(label: str, values: list[float]) -> dict:
    p50, p95 = percentile(values, 50), percentile(values, 95)
    return {"label": label, "n": len(values), "p50_ms": None if p50 is None else round(p50),
            "p95_ms": None if p95 is None else round(p95)}


def latency_stats(runs: dict[str, list[dict]]) -> dict:
    """Time to flag from recorded runs {call id: events}. A finding counts once per phase (its first appearance);
    good-practice items are not flags. 'First flag' is the earliest appearance of each finding."""
    first: list[float] = []
    by_phase: dict[str, list[float]] = {"fast": [], "deep": []}
    llm: list[float] = []
    for cid, events in runs.items():
        seen_any: set[str] = set()
        seen_phase: set[tuple[str, str]] = set()
        for e in events:
            if e.get("type") != "finding.detected":
                continue
            d = e["data"]
            lat = d.get("latency") or {}
            if d.get("kind") == "good_practice" or "total_ms" not in lat:
                continue
            key = f"{cid}:{d['id']}"
            if key not in seen_any:
                seen_any.add(key)
                first.append(lat["total_ms"])
            if (key, d["phase"]) not in seen_phase and d["phase"] in by_phase:
                seen_phase.add((key, d["phase"]))
                by_phase[d["phase"]].append(lat["total_ms"])
                if d["phase"] == "deep" and lat.get("llm_ms"):
                    llm.append(lat["llm_ms"])
    rows = [_row("First flag (either check)", first), *(_row(label, by_phase[k]) for k, label in PHASES),
            _row("Language model step", llm)]
    return {"calls": sorted(runs), "rows": rows,
            "method": "Time from the end of the flagged speech to the flag appearing, as recorded in the saved runs; "
                      "percentiles by linear interpolation; each finding counted once per check."}


def _replays(root: Path) -> dict[str, list[dict]]:
    out = {}
    for p in sorted(root.glob("c*.json")):  # committed recordings only (not the private _runs folder)
        try:
            out[p.stem] = json.loads(p.read_text(encoding="utf-8"))["events"]
        except (OSError, ValueError, KeyError):
            continue
    return out


def eval_payload() -> dict:
    """{results: eval_results.json or None, latency: time-to-flag statistics}."""
    path = settings.data_dir / "eval" / "eval_results.json"
    try:
        results = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        results = None
    return {"results": results, "latency": latency_stats(_replays(settings.data_dir / "replay"))}
