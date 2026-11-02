"""Team compliance numbers from hand-made calls (no files, no network)."""
from app.manager.aggregate import aggregate, in_range, status_of, top_rule

AGENTS = [{"id": "A1", "name": "Alpha", "team": "T"}, {"id": "A2", "name": "Beta", "team": "T"},
          {"id": "A3", "name": "Gamma", "team": "T"}]


def call(cid, agent, day, risk=0, hour=11, finds=(), time="11:00"):
    """finds = [(rule, kind, turn)]"""
    return {"call_id": cid, "agent_id": agent, "call_date": day, "call_time": time, "hour": hour, "risk_peak": risk,
            "findings": [{"rule_id": r, "kind": k, "turn_idx": t, "quote": "q"} for r, k, t in finds]}


def agent(rows, aid):
    return next(a for a in rows["agents"] if a["id"] == aid)


def test_status_thresholds_at_the_edges():
    assert status_of(3, 0, 0, 0) == "excellent"
    assert status_of(2, 0, 0, 0) == "too_few_calls"  # clean but too few calls: not Watch (Watch needs a violation)
    assert status_of(3, 1, 0, 5) == "watch"
    assert status_of(4, 3, 1, 10) == "watch"  # one R3/R4/R5 violation is not enough
    assert status_of(4, 3, 2, 10) == "needs_training"
    assert status_of(4, 1, 0, 39.9) == "watch"
    assert status_of(4, 1, 0, 40) == "needs_training"
    assert status_of(0, 0, 0, None) == "no_calls"


def test_only_r3_r4_r5_count_for_the_serious_threshold():
    calls = [call("c1", "A1", "2026-10-12", finds=[("R1", "violation", 1), ("R2", "advisory", 3), ("R6", "violation", 5)]),
             call("c2", "A1", "2026-10-13"), call("c3", "A1", "2026-10-14")]
    a = agent(aggregate(calls, AGENTS), "A1")
    assert (a["violations"], a["serious_violations"], a["status"]) == (3, 0, "watch")
    calls[1]["findings"] = [{"rule_id": "R3", "kind": "violation", "turn_idx": 7, "quote": ""},
                            {"rule_id": "R4", "kind": "violation", "turn_idx": 9, "quote": ""}]
    assert agent(aggregate(calls, AGENTS), "A1")["status"] == "needs_training"


def test_agent_with_no_calls_stays_listed():
    out = aggregate([call("c1", "A1", "2026-10-12")], AGENTS)
    a = agent(out, "A3")
    assert (a["calls"], a["violations"], a["avg_risk"], a["peak_risk"], a["status"], a["top_rule"]) == (0, 0, None, None, "no_calls", None)
    assert out["kpis"]["agents"] == 1


def test_empty_selection_has_no_rates():
    out = aggregate([], AGENTS)
    k = out["kpis"]
    assert (k["calls"], k["violation_rate"], k["avg_risk"], k["good_practice_rate"]) == (0, None, None, None)
    assert out["by_day"] == [] and out["by_hour"] == [] and out["attention"] == []


def test_top_rule_ties_go_to_the_heavier_rule_then_the_lower_number():
    assert top_rule({"R2": 2, "R5": 2}) == "R5"
    assert top_rule({"R3": 1, "R4": 1}) == "R4"  # weights 30 and 35
    assert top_rule({"R4": 1, "R5": 1}) == "R4"  # same weight: lower rule number
    assert top_rule({"R1": 1, "R3": 3}) == "R3"
    assert top_rule({}) is None


def test_same_rule_twice_in_a_turn_counts_once_and_needs_review_is_not_a_violation():
    c = call("c1", "A1", "2026-10-12", finds=[("R3", "violation", 7), ("R3", "violation", 7), ("R6", "needs_review", 5),
                                              ("G1", "good_practice", 3)])
    a = agent(aggregate([c], AGENTS), "A1")
    assert (a["violations"], a["needs_review"], a["good_practice"], a["calls_with_violation"]) == (1, 1, 1, 1)


def test_date_filter_is_inclusive_and_open_ended():
    assert in_range("2026-10-12", "2026-10-12", "2026-10-12")
    assert not in_range("2026-10-11", "2026-10-12", None)
    assert not in_range("2026-10-13", None, "2026-10-12")
    calls = [call(f"c{i}", "A1", f"2026-10-{12 + i}") for i in range(4)]
    assert aggregate(calls, AGENTS, "2026-10-13", "2026-10-14")["n_calls"] == 2
    assert aggregate(calls, AGENTS, None, "2026-10-13")["n_calls"] == 2
    assert aggregate(calls, AGENTS, "2026-11-01", None)["n_calls"] == 0


def test_filter_changes_status_and_agent_aggregates():
    calls = [call("c1", "A1", "2026-10-12", finds=[("R3", "violation", 7)], risk=30),
             call("c2", "A1", "2026-10-13", finds=[("R5", "violation", 7)], risk=35), call("c3", "A1", "2026-10-20")]
    assert agent(aggregate(calls, AGENTS), "A1")["status"] == "needs_training"
    late = aggregate(calls, AGENTS, "2026-10-15", None)
    assert (agent(late, "A1")["calls"], agent(late, "A1")["status"]) == (1, "too_few_calls")


def test_kpis_equal_sums_over_calls():
    calls = [call("c1", "A1", "2026-10-12", risk=30, finds=[("R3", "violation", 7), ("R2", "advisory", 3)]),
             call("c2", "A2", "2026-10-12", risk=0, finds=[("G1", "good_practice", 3)]),
             call("c3", "A2", "2026-10-14", risk=20, hour=7, finds=[("R1", "violation", 1)])]
    out = aggregate(calls, AGENTS)
    k = out["kpis"]
    assert (k["calls"], k["violations"], k["calls_with_violation"], k["good_practice_calls"]) == (3, 3, 2, 1)
    assert k["avg_risk"] == round(50 / 3, 1)
    assert k["violations"] == sum(a["violations"] for a in out["agents"]) == sum(out["rule_totals"].values())
    assert sum(d["violations"] for d in out["by_day"]) == 3 and sum(d["calls"] for d in out["by_day"]) == 3


def test_by_day_fills_quiet_days_and_by_hour_marks_r1_calls():
    calls = [call("c1", "A1", "2026-10-12"), call("c2", "A1", "2026-10-15", hour=7, finds=[("R1", "violation", 1)])]
    out = aggregate(calls, AGENTS)
    assert [d["date"] for d in out["by_day"]] == ["2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15"]
    assert out["by_day"][1] == {"date": "2026-10-13", "calls": 0, "violations": 0}
    hrs = {h["hour"]: h for h in out["by_hour"]}
    assert sorted(hrs) == list(range(7, 12)) and hrs[7]["r1_calls"] == 1 and hrs[11]["r1_calls"] == 0 and hrs[9]["calls"] == 0


def test_first_half_vs_second_half_and_risk_trend_order():
    calls = [call("c1", "A1", "2026-10-12", risk=50, finds=[("R3", "violation", 7)]), call("c2", "A1", "2026-10-13", risk=10),
             call("c3", "A1", "2026-10-14", risk=0), call("c4", "A1", "2026-10-15", risk=0)]
    a = agent(aggregate(list(reversed(calls)), AGENTS), "A1")
    assert a["risk_trend"] == [50, 10, 0, 0]
    assert a["first_half_vs_second_half"] == {"first": 1, "second": 0, "calls_first": 2, "calls_second": 2}


def test_leaderboard_order_and_attention_cards():
    calls = [call("a", "A1", "2026-10-12", risk=45, finds=[("R3", "violation", 7)]), call("b", "A2", "2026-10-12", finds=[("R2", "advisory", 3)]),
             call("c", "A3", "2026-10-12"), call("d", "A3", "2026-10-13"), call("e", "A3", "2026-10-14")]
    out = aggregate(calls, AGENTS)
    assert [a["id"] for a in out["agents"]] == ["A1", "A2", "A3"]  # needs training, watch, excellent
    assert out["attention"] == ["A1", "A2"]  # the excellent agent is never an attention card
    ties = aggregate([call("a", "A1", "2026-10-12", finds=[("R2", "advisory", 3)]), call("b", "A2", "2026-10-12", finds=[("R2", "advisory", 3)])], AGENTS)
    assert [a["name"] for a in ties["agents"][:2]] == ["Alpha", "Beta"]  # equal rows are ordered by name


def test_needs_review_is_counted_per_rule_and_never_as_a_violation():
    calls = [call("c1", "A1", "2026-10-12", finds=[("R6", "needs_review", 5), ("R6", "needs_review", 5), ("R6", "needs_review", 9)]),
             call("c2", "A1", "2026-10-13", finds=[("R3", "needs_review", 4)])]
    out = aggregate(calls, AGENTS)
    a = agent(out, "A1")
    assert a["violations"] == 0 and a["by_rule"]["R6"] == 0
    assert a["review_by_rule"]["R6"] == 2 and a["review_by_rule"]["R3"] == 1
    assert out["review_totals"]["R6"] == 2 and out["rule_totals"]["R6"] == 0
    assert a["status"] == "too_few_calls"


def _batch(n, bad_in_second):
    """n calls on consecutive days; the first n//2 clean, then `bad_in_second` of the rest with a violation."""
    days = [f"2026-10-{12 + i:02d}" for i in range(n)]
    out = []
    for i, d in enumerate(days):
        late_bad = i >= n // 2 and i - n // 2 < bad_in_second
        out.append(call(f"c{i}", "A1", d, risk=40 if late_bad else 0, finds=[("R3", "violation", 7)] if late_bad else [("G1", "good_practice", 3)]))
    return out


def test_kpi_deltas_need_eight_calls_in_each_half():
    assert aggregate(_batch(15, 2), AGENTS)["kpi_deltas"] is None  # halves of 7 and 8
    assert aggregate([], AGENTS)["kpi_deltas"] is None
    d = aggregate(_batch(16, 4), AGENTS)["kpi_deltas"]
    assert d["first_calls"] == d["second_calls"] == 8
    assert d["violation_rate"] == 0.5 and d["avg_risk"] == 20.0 and d["good_practice_rate"] == -0.5
    assert aggregate(_batch(16, 4), AGENTS, "2026-10-20", None)["kpi_deltas"] is None  # a narrower range can drop them


def test_status_rule_text_names_the_too_few_calls_case():
    from app.manager.aggregate import STATUS_RULE
    assert "Too few calls" in STATUS_RULE and "Watch: at least one violation" in STATUS_RULE
