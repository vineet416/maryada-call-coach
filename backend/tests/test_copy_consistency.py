"""Example call per agent (Manager) and languages heard in the recordings: hand-made data plus the current saved data."""
import pytest
from app.evaluation import languages_heard
from app.manager.aggregate import _violations, example_call_id
from app.manager.data import load_saved, manager_payload


def call(cid, risk, finds):
    return {"call_id": cid, "risk_peak": risk, "findings": [{"rule_id": r, "kind": "violation", "turn_idx": t, "quote": "q"} for r, t in finds]}


def test_example_call_has_the_most_violations_of_the_rule():
    calls = [call("c1", 90, [("R3", 5)]), call("c2", 40, [("R3", 5), ("R3", 7)]), call("c3", 95, [("R4", 5)])]
    assert example_call_id(calls, "R3") == "c2"  # two R3 beat one, despite lower risk
    assert example_call_id(calls, None) is None
    assert example_call_id(calls, "R6") is None


def test_example_call_ties_go_to_higher_risk_then_lower_id():
    calls = [call("c2", 50, [("R3", 5)]), call("c1", 50, [("R3", 5)]), call("c3", 70, [("R3", 5)])]
    assert example_call_id(calls, "R3") == "c3"
    assert example_call_id(calls[:2], "R3") == "c1"


def test_languages_heard_from_tokens():
    ev = {"c1": [{"type": "transcript.final", "data": {"tokens": [{"lang": "hi"}, {"lang": "en-IN"}, {"lang": ""}]}},
                 {"type": "turn.started", "data": {}}]}
    assert languages_heard(ev) == ["en", "hi"]
    assert languages_heard({}) == []


@pytest.mark.skipif(load_saved() is None, reason="no saved manager data")
def test_current_data_each_linked_call_has_a_violation_of_the_agents_top_rule():
    p = manager_payload(None, None)
    calls = {c["call_id"]: c for c in p["calls"]}
    checked = 0
    for a in p["agents"]:
        if a["top_rule"] is None:
            assert a["example_call_id"] is None
            continue
        mine = [c for c in p["calls"] if c["agent_id"] == a["id"]]
        linked = calls[a["example_call_id"]]
        assert linked["agent_id"] == a["id"]
        rule = a["top_rule"]

        def n(c, rule=rule):
            return sum(1 for f in _violations(c) if f["rule_id"] == rule)

        assert n(linked) >= 1
        assert n(linked) == max(n(c) for c in mine)
        checked += 1
    assert checked > 0
