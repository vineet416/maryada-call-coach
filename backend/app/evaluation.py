"""Evaluation page data: the committed results file and the time-to-flag statistics from the committed recordings.

The numbers in eval_results.json are written by tools/run_eval.py and passed on unchanged. The only calculation here is
the "after human review of extras" line (review_adjusted), from the author's verdicts in adjudication.json; no model or
speech service is called and the frozen labels are never changed.
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
            d = e.get("data") if isinstance(e, dict) and e.get("type") == "finding.detected" else None
            if not isinstance(d, dict):
                continue
            lat = d.get("latency")
            if d.get("kind") == "good_practice" or not isinstance(lat, dict) or not isinstance(lat.get("total_ms"), int | float):
                continue
            key, phase = f"{cid}:{d.get('id')}", d.get("phase")
            if not isinstance(phase, str):
                continue
            if key not in seen_any:
                seen_any.add(key)
                first.append(lat["total_ms"])
            if (key, phase) not in seen_phase and phase in by_phase:
                seen_phase.add((key, phase))
                by_phase[phase].append(lat["total_ms"])
                if phase == "deep" and lat.get("llm_ms"):
                    llm.append(lat["llm_ms"])
    rows = [_row("First flag (either check)", first), *(_row(label, by_phase[k]) for k, label in PHASES),
            _row("Language model step", llm)]
    return {"calls": sorted(runs), "rows": rows,
            "method": "Time from the end of the flagged speech to the flag appearing, as recorded in the saved runs; "
                      "percentiles by linear interpolation; each finding counted once per check."}


def languages_heard(runs: dict[str, list[dict]]) -> list[str]:
    """Sorted base language codes (hi, en, mr...) found in the transcript tokens of recorded runs."""
    found: set[str] = set()
    for events in runs.values():
        for e in events:
            if isinstance(e, dict) and e.get("type") == "transcript.final" and isinstance(e.get("data"), dict):
                for t in e["data"].get("tokens") or []:
                    if isinstance(t, dict) and isinstance(t.get("lang"), str) and t["lang"]:
                        found.add(t["lang"].split("-")[0].lower())
    return sorted(found)


VERDICTS = ("real", "unsure", "not_a_violation")


def _round(x: float | None) -> float | None:
    return None if x is None else round(x, 4)


def _adjust_view(prf: dict, extras: list, verdicts: dict) -> dict:
    """One view (strict or with review). Counts: flags = tp + fp. Real extras are correct flags, not-a-violation stay false,
    unsure is a range (all false = low, all correct = high). Recall is against the frozen labels and does not change."""
    n = {v: sum(1 for u in extras if verdicts.get(tuple(u)) == v) for v in VERDICTS}
    flags = prf["tp"] + prf["fp"]
    recall = prf["r"]

    def prec_f1(correct: int) -> tuple[float | None, float | None]:
        p = correct / flags if flags else None
        f1 = None if p is None or recall is None else (0.0 if p + recall == 0 else 2 * p * recall / (p + recall))
        return p, f1

    low, high = prec_f1(prf["tp"] + n["real"]), prec_f1(prf["tp"] + n["real"] + n["unsure"])
    return {"flags": flags, "correct_original": prf["tp"], "correct_low": prf["tp"] + n["real"],
            "correct_high": prf["tp"] + n["real"] + n["unsure"], "extras_real": n["real"], "extras_unsure": n["unsure"],
            "extras_not_a_violation": n["not_a_violation"], "precision_original": _round(prf["p"]),
            "precision_low": _round(low[0]), "precision_high": _round(high[0]), "recall": _round(recall),
            "f1_low": _round(low[1]), "f1_high": _round(high[1])}


def review_adjusted(run: dict, held_out_calls: list[str], items: list[dict]) -> dict | None:
    """{group: {strict: ..., with_review: ...}} for the pooled and the held-out calls of one run, or None without data."""
    verdicts = {(i["call"], i["turn"], i["rule"]): i["verdict"] for i in items if i.get("verdict") in VERDICTS}
    allv = run.get("all")
    if not isinstance(allv, dict) or not verdicts:
        return None
    out = {}
    for group, calls in (("all", None), ("held_out", set(held_out_calls))):
        rows = [c for c in allv.get("per_call", []) if calls is None or c["call_id"] in calls]
        score = run.get(group)
        if not rows or not isinstance(score, dict):
            continue
        out[group] = {
            "strict": _adjust_view(score["overall"]["strict"], [u for c in rows for u in c["false_alarms"]], verdicts),
            "with_review": _adjust_view(score["overall"]["with_review"], [u for c in rows for u in c["false_alarms_with_review"]], verdicts),
        }
    return out or None


def _review(results: dict | None, root: Path) -> dict | None:
    try:
        adj = json.loads((root / "adjudication.json").read_text(encoding="utf-8"))
        items = adj["items"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not (results and isinstance(items, list)):
        return None
    held = (results.get("splits") or {}).get("held_out") or []
    adjusted = {}
    for cond, run in (results.get("full") or {}).items():
        if isinstance(run, dict):
            a = review_adjusted(run, held, items)
            if a:
                adjusted[f"full/{cond}"] = a
    return {"reviewer": adj.get("reviewer"), "reviewed_on": adj.get("reviewed_on"), "scope": adj.get("scope"),
            "items": items, "adjusted": adjusted}


def _engine_changes(root: Path) -> list:
    try:
        changes = json.loads((root / "engine_changes.json").read_text(encoding="utf-8"))["changes"]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    return changes if isinstance(changes, list) else []


def _replays(root: Path) -> dict[str, list[dict]]:
    out = {}
    for p in sorted(root.glob("c*.json")):  # committed recordings only (not the private _runs folder)
        try:
            events = json.loads(p.read_text(encoding="utf-8"))["events"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if isinstance(events, list):
            out[p.stem] = events
    return out


def eval_payload() -> dict:
    """{results: eval_results.json or None, review: adjudication and adjusted precision or None, latency: time-to-flag statistics}."""
    path = settings.data_dir / "eval" / "eval_results.json"
    try:
        results = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        results = None
    if not (isinstance(results, dict) and isinstance(results.get("full"), dict)
            and isinstance(results.get("ablation_llm_off"), dict)):
        results = None  # not a results file: the page shows "no results published"
    return {"results": results, "review": _review(results, settings.data_dir / "eval"),
            "engine_changes": _engine_changes(settings.data_dir / "eval"),
            "latency": latency_stats(_replays(settings.data_dir / "replay")),
            "languages": languages_heard(_replays(settings.data_dir / "replay"))}
