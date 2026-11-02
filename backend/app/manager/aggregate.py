"""Team compliance numbers from per-call results (pure: no files, no network, no model).

A call is {call_id, agent_id, call_date (ISO), hour (0-23), risk_peak, findings: [{rule_id, kind, turn_idx, quote}]}.
A *violation* here is a finding of kind violation or advisory (the evaluation's positive predictions). Findings of kind
needs_review are counted apart and never as violations; good practice (G1) is counted per call, not per finding.
"""
from datetime import date, timedelta

RULES = ("R1", "R2", "R3", "R4", "R5", "R6")
SERIOUS = ("R3", "R4", "R5")
VIOLATION_KINDS = ("violation", "advisory")
EXCELLENT_MIN_CALLS = 3
TRAINING_MIN_SERIOUS = 2
TRAINING_AVG_RISK = 40
# Rule weight for breaking ties between equally frequent rules (same numbers as the risk meter).
_WEIGHT = {"R3": 30, "R5": 35, "R4": 35, "R1": 20, "R2": 8, "R6": 10}
STATUS_ORDER = {"needs_training": 0, "watch": 1, "excellent": 2, "too_few_calls": 3, "no_calls": 4}
DELTA_MIN_CALLS = 8  # each half of the period needs this many calls before a KPI delta is shown


STATUS_RULE = (f"Excellent: no violations in at least {EXCELLENT_MIN_CALLS} calls. Needs training: {TRAINING_MIN_SERIOUS} or more "
               f"violations of {', '.join(SERIOUS[:-1])} or {SERIOUS[-1]}, or an average risk of {TRAINING_AVG_RISK} or more. Watch: at least one violation otherwise. "
               f"Too few calls: no violations, but fewer than {EXCELLENT_MIN_CALLS} calls.")


def in_range(call_date: str, start: str | None, end: str | None) -> bool:
    """Inclusive ISO-date bounds; either may be None. ISO dates compare correctly as strings."""
    return (start is None or call_date >= start) and (end is None or call_date <= end)


def _violations(call: dict) -> list[dict]:
    """One per (turn, rule): the same rule twice in one turn counts once."""
    seen, out = set(), []
    for f in call["findings"]:
        key = (f["turn_idx"], f["rule_id"])
        if f["rule_id"] in RULES and f["kind"] in VIOLATION_KINDS and key not in seen:
            seen.add(key)
            out.append(f)
    return out


def _count_kind(call: dict, kind: str) -> int:
    return len({(f["turn_idx"], f["rule_id"]) for f in call["findings"] if f["rule_id"] in RULES and f["kind"] == kind})


def _has_good(call: dict) -> bool:
    return any(f["kind"] == "good_practice" for f in call["findings"])


def top_rule(by_rule: dict[str, int]) -> str | None:
    """Most frequent rule; ties go to the heavier rule (risk weight), then to the lower rule number. None if all zero."""
    rules = [r for r in RULES if by_rule.get(r, 0) > 0]
    return min(rules, key=lambda r: (-by_rule[r], -_WEIGHT[r], r)) if rules else None


def status_of(n_calls: int, violations: int, serious: int, avg_risk: float | None) -> str:
    """Fixed rule: needs_training = at least 2 R3/R4/R5 violations or average risk of 40 or more; excellent = no
    violations in at least 3 calls; watch = any other agent with a violation; too_few_calls = no violations but fewer
    than 3 calls (docs/09 leaves this case open: neutral, never Watch); no_calls = nothing to judge."""
    if n_calls == 0:
        return "no_calls"
    if serious >= TRAINING_MIN_SERIOUS or (avg_risk is not None and avg_risk >= TRAINING_AVG_RISK):
        return "needs_training"
    if violations == 0:
        return "excellent" if n_calls >= EXCELLENT_MIN_CALLS else "too_few_calls"
    return "watch"


def example_call_id(calls: list[dict], rule: str | None) -> str | None:
    """The agent's own call with the most violations of `rule` (the agent's top rule); ties go to the higher peak risk,
    then to the lower call id. None when there is no top rule."""
    if rule is None:
        return None
    scored = [(sum(1 for f in _violations(c) if f["rule_id"] == rule), c) for c in calls]
    scored = [(n, c) for n, c in scored if n > 0]
    if not scored:
        return None
    return min(scored, key=lambda nc: (-nc[0], -nc[1]["risk_peak"], nc[1]["call_id"]))[1]["call_id"]


def _agent_row(agent: dict, calls: list[dict]) -> dict:
    calls = sorted(calls, key=lambda c: (c["call_date"], c.get("call_time", ""), c["call_id"]))
    by_rule = dict.fromkeys(RULES, 0)
    for c in calls:
        for f in _violations(c):
            by_rule[f["rule_id"]] += 1
    review_by_rule = dict.fromkeys(RULES, 0)
    for c in calls:
        for rule, _turn in {(f["rule_id"], f["turn_idx"]) for f in c["findings"] if f["kind"] == "needs_review" and f["rule_id"] in RULES}:
            review_by_rule[rule] += 1
    violations = sum(by_rule.values())
    serious = sum(by_rule[r] for r in SERIOUS)
    risks = [c["risk_peak"] for c in calls]
    avg = round(sum(risks) / len(risks), 1) if risks else None
    half = len(calls) // 2  # earlier calls / later calls; with an odd count the middle call is in the later half
    first, second = calls[:half], calls[half:]
    topics = sorted((r for r in RULES if by_rule[r]), key=lambda r: (-by_rule[r], -_WEIGHT[r], r))
    status = status_of(len(calls), violations, serious, avg)
    return {
        "id": agent["id"], "name": agent["name"], "team": agent.get("team", ""),
        "calls": len(calls), "violations": violations, "serious_violations": serious,
        "calls_with_violation": sum(1 for c in calls if _violations(c)),
        "advisories": sum(_count_kind(c, "advisory") for c in calls),
        "needs_review": sum(_count_kind(c, "needs_review") for c in calls),
        "good_practice": sum(1 for c in calls if _has_good(c)),
        "avg_risk": avg, "peak_risk": max(risks) if risks else None,
        "by_rule": by_rule, "review_by_rule": review_by_rule, "top_rule": top_rule(by_rule),
        "example_call_id": example_call_id(calls, top_rule(by_rule)), "status": status,
        "risk_trend": risks,  # one value per call, oldest first (the sparkline)
        "first_half_vs_second_half": {"first": sum(len(_violations(c)) for c in first),
                                      "second": sum(len(_violations(c)) for c in second),
                                      "calls_first": len(first), "calls_second": len(second)},
        "training_flag": status == "needs_training", "training_topics": topics,
    }


def _days(calls: list[dict]) -> list[dict]:
    """Every date from the first to the last call, so quiet days show as zero."""
    if not calls:
        return []
    per: dict[str, list[int]] = {}
    for c in calls:
        row = per.setdefault(c["call_date"], [0, 0])
        row[0] += 1
        row[1] += len(_violations(c))
    d, last = date.fromisoformat(min(per)), date.fromisoformat(max(per))
    out = []
    while d <= last:
        n, v = per.get(d.isoformat(), [0, 0])
        out.append({"date": d.isoformat(), "calls": n, "violations": v})
        d += timedelta(days=1)
    return out


def _hours(calls: list[dict]) -> list[dict]:
    """Every hour from the first to the last call hour; `r1_calls` = calls in that hour with an R1 finding."""
    if not calls:
        return []
    per: dict[int, list[int]] = {}
    for c in calls:
        row = per.setdefault(c["hour"], [0, 0, 0])
        row[0] += 1
        row[1] += len(_violations(c))
        row[2] += any(f["rule_id"] == "R1" for f in _violations(c))
    return [{"hour": h, "calls": per.get(h, [0, 0, 0])[0], "violations": per.get(h, [0, 0, 0])[1],
             "r1_calls": per.get(h, [0, 0, 0])[2]} for h in range(min(per), max(per) + 1)]


def _rates(calls: list[dict]) -> dict:
    n = len(calls)
    return {"violation_rate": sum(1 for c in calls if _violations(c)) / n,
            "avg_risk": sum(c["risk_peak"] for c in calls) / n,
            "clean_rate": sum(1 for c in calls if not _violations(c)) / n}


def _deltas(calls: list[dict]) -> dict | None:
    """Later half minus earlier half (calls in date order; the middle call of an odd count is in the later half) for the
    rate KPIs. None unless both halves have at least DELTA_MIN_CALLS calls (docs/09 4.1)."""
    ordered = sorted(calls, key=lambda c: (c["call_date"], c.get("call_time", ""), c["call_id"]))
    half = len(ordered) // 2
    if half < DELTA_MIN_CALLS:
        return None
    a, b = _rates(ordered[:half]), _rates(ordered[half:])
    return {k: round(b[k] - a[k], 4 if k != "avg_risk" else 1) for k in a} | {"first_calls": half, "second_calls": len(ordered) - half}


def aggregate(calls: list[dict], agents: list[dict], start: str | None = None, end: str | None = None) -> dict:
    """Everything the dashboard shows for the calls dated start..end (inclusive; None = open). Agents with no calls
    in range stay in the list with status "no_calls"."""
    chosen = [c for c in calls if in_range(c["call_date"], start, end)]
    rows = [_agent_row(a, [c for c in chosen if c["agent_id"] == a["id"]]) for a in agents]
    rows.sort(key=lambda r: (STATUS_ORDER[r["status"]], -r["violations"], -(r["avg_risk"] or 0), r["name"]))
    totals = dict.fromkeys(RULES, 0)
    for r in rows:
        for k in RULES:
            totals[k] += r["by_rule"][k]
    n = len(chosen)
    with_v = sum(1 for c in chosen if _violations(c))
    risks = [c["risk_peak"] for c in chosen]
    kpis = {
        "calls": n, "agents": sum(1 for r in rows if r["calls"]), "violations": sum(totals.values()),
        "calls_with_violation": with_v, "violation_rate": with_v / n if n else None,
        "avg_risk": round(sum(risks) / n, 1) if n else None,
        "clean_calls": n - with_v, "clean_rate": (n - with_v) / n if n else None,
    }
    review_totals = dict.fromkeys(RULES, 0)
    for r in rows:
        for k in RULES:
            review_totals[k] += r["review_by_rule"][k]
    attention = [r["id"] for r in rows if r["status"] in ("needs_training", "watch") and r["violations"]][:3]
    return {"n_calls": n, "kpis": kpis, "agents": rows, "rule_totals": totals, "review_totals": review_totals,
            "kpi_deltas": _deltas(chosen), "by_day": _days(chosen),
            "by_hour": _hours(chosen), "attention": attention,
            "calls": sorted(chosen, key=lambda c: (c["call_date"], c.get("call_time", ""), c["call_id"]))}
