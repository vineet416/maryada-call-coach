"""Scoring for the evaluation (pure functions; no files, no network).

Unit = (call, agent turn, rule). A label is a unit the script marks as a violation; a detection is a unit where the
engine produced a finding. Per unit the strongest kind wins (violation > advisory > needs_review).

Positive predictions are `violation` and `advisory`. `needs_review` is reported separately: "strict" counts only the
positives, "with_review" also counts needs_review as a detection (for precision and recall alike). G1 (good practice)
is not labelled, so it never enters precision or recall; it has its own line.
"""
import hashlib
import json

RULES = ("R1", "R2", "R3", "R4", "R5", "R6")
POSITIVE = ("violation", "advisory")
_RANK = {"needs_review": 1, "advisory": 2, "violation": 3}


def label_units(scenarios: list[dict]) -> set[tuple[str, int, str]]:
    """Labelled units (call, turn number, rule) from the scenario files. Turn numbers start at 1; G1 is never labelled."""
    out = set()
    for sc in scenarios:
        for i, turn in enumerate(sc["turns"], 1):
            for lab in turn.get("L") or []:
                if lab[0] in RULES:
                    out.add((sc["id"], i, lab[0]))
    return out


def labels_hash(scenarios: list[dict]) -> str:
    """Stable hash of the labels and of which calls exist, written into every results file."""
    units = sorted(label_units(scenarios))
    calls = sorted(sc["id"] for sc in scenarios)
    return hashlib.sha256(json.dumps({"calls": calls, "units": units}).encode()).hexdigest()[:16]


def prf(tp: int, fp: int, fn: int) -> dict:
    """Precision, recall, F1; None where the denominator is zero (undefined, not 0 and not 1)."""
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f1 = None if p is None or r is None else (0.0 if p + r == 0 else 2 * p * r / (p + r))
    return {"tp": tp, "fp": fp, "fn": fn, "p": p, "r": r, "f1": f1}


def unit_kinds(detections: list[dict]) -> dict[tuple[str, int, str], str]:
    """Strongest kind per (call, turn, rule) for R1-R6. Items: {call, turn, rule, kind}. Other rules and kinds are ignored."""
    out: dict[tuple[str, int, str], str] = {}
    for d in detections:
        if d["rule"] not in RULES or d["kind"] not in _RANK:
            continue
        k = (d["call"], d["turn"], d["rule"])
        if k not in out or _RANK[d["kind"]] > _RANK[out[k]]:
            out[k] = d["kind"]
    return out


def _count(labels: set, kinds: dict, accept: tuple[str, ...]) -> tuple[int, int, int]:
    pred = {u for u, k in kinds.items() if k in accept}
    return len(pred & labels), len(pred - labels), len(labels - pred)


def _block(labels: set, kinds: dict) -> dict:
    strict = prf(*_count(labels, kinds, POSITIVE))
    review = prf(*_count(labels, kinds, (*POSITIVE, "needs_review")))
    nr = {u for u, k in kinds.items() if k == "needs_review"}
    return {"strict": strict, "with_review": review,
            "needs_review": {"on_label": len(nr & labels), "off_label": len(nr - labels)}}


def score(scenarios: list[dict], detections: list[dict], calls: list[str] | None = None) -> dict:
    """Scores for `calls` (default: every scenario). Detections of other calls are ignored."""
    ids = set(calls) if calls is not None else {sc["id"] for sc in scenarios}
    chosen = [sc for sc in scenarios if sc["id"] in ids]
    labels = {u for u in label_units(chosen)}
    kinds = {u: k for u, k in unit_kinds([d for d in detections if d["call"] in ids]).items()}
    per_rule = {r: _block({u for u in labels if u[2] == r}, {u: k for u, k in kinds.items() if u[2] == r}) for r in RULES}
    per_call, negatives = [], {"calls": 0, "calls_with_false_alarm": 0, "false_alarm_units": 0,
                               "calls_with_false_alarm_with_review": 0}
    for sc in chosen:
        cid = sc["id"]
        exp = {u for u in labels if u[0] == cid}
        got = {u: k for u, k in kinds.items() if u[0] == cid}
        hit = {u for u, k in got.items() if k in POSITIVE} & exp
        hit_r = {u for u, k in got.items() if k in (*POSITIVE, "needs_review")} & exp
        extra = {u for u, k in got.items() if k in POSITIVE} - exp
        extra_r = {u for u, k in got.items() if k in (*POSITIVE, "needs_review")} - exp
        per_call.append({
            "call_id": cid, "hard_negative": bool(sc.get("hard_negative")),
            "expected": sorted(exp, key=lambda u: (u[1], u[2])),
            "hit": sorted(hit, key=lambda u: (u[1], u[2])), "hit_with_review": sorted(hit_r, key=lambda u: (u[1], u[2])),
            "missed": sorted(exp - hit, key=lambda u: (u[1], u[2])),
            "missed_with_review": sorted(exp - hit_r, key=lambda u: (u[1], u[2])),
            "false_alarms": sorted(extra, key=lambda u: (u[1], u[2])),
            "false_alarms_with_review": sorted(extra_r, key=lambda u: (u[1], u[2])),
            "expected_rules": sorted({u[2] for u in exp}),
            "caught_rules": sorted({u[2] for u in hit}), "caught_rules_with_review": sorted({u[2] for u in hit_r})})
        if not exp:  # a call with no labels: any positive prediction is a false alarm
            negatives["calls"] += 1
            negatives["calls_with_false_alarm"] += bool(extra)
            negatives["calls_with_false_alarm_with_review"] += bool(extra_r)
            negatives["false_alarm_units"] += len(extra)
    exp_rules = sum(len(c["expected_rules"]) for c in per_call)  # call-level recall: expected rule caught at least once
    call_level = {"expected": exp_rules, "caught": sum(len(c["caught_rules"]) for c in per_call),
                  "caught_with_review": sum(len(c["caught_rules_with_review"]) for c in per_call)}
    g1_units = {(d["call"], d["turn"]) for d in detections if d["rule"] == "G1" and d["call"] in ids}
    g1 = {"findings": sum(1 for d in detections if d["rule"] == "G1" and d["call"] in ids), "agent_turns_with_g1": len(g1_units)}
    return {"n_calls": len(chosen), "per_rule": per_rule, "overall": _block(labels, kinds), "per_call": per_call,
            "negatives": negatives, "call_level": call_level, "g1": g1}
