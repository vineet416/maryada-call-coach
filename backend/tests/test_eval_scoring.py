"""Scoring of the evaluation: hand-made scenarios and detections (no STT, no model, no HTTP)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import eval_scoring as es


def sc(cid, labels=(), n=7, hard=False):
    """Scenario with `n` turns; labels = [(turn, rule)]."""
    turns = [{"s": "A", "t": "x"} for _ in range(n)]
    for t, r in labels:
        turns[t - 1].setdefault("L", []).append([r, "x"])
    return {"id": cid, "turns": turns, "hard_negative": hard}


def det(call, turn, rule, kind="violation"):
    return {"call": call, "turn": turn, "rule": rule, "kind": kind}


SCEN = [sc("c1", [(1, "R1"), (5, "R3"), (5, "R3"), (7, "R5")]), sc("c2", [(3, "R6")]), sc("c3", hard=True)]


def test_label_units_collapse_duplicates_and_ignore_other_rules():
    s = [sc("a", [(2, "R3"), (2, "R3"), (4, "G1")])]
    assert es.label_units(s) == {("a", 2, "R3")}


def test_prf_values_and_undefined():
    r = es.prf(2, 1, 2)
    assert (r["p"], r["r"]) == (2 / 3, 0.5)
    assert abs(r["f1"] - 4 / 7) < 1e-9
    e = es.prf(0, 0, 0)
    assert e["p"] is None and e["r"] is None and e["f1"] is None
    z = es.prf(0, 2, 2)
    assert z["p"] == 0 and z["r"] == 0 and z["f1"] == 0.0
    assert es.prf(0, 3, 0)["r"] is None  # nothing to find: recall undefined, precision 0


def test_tp_fp_fn_per_rule_strict():
    dets = [det("c1", 1, "R1"), det("c1", 5, "R3"), det("c1", 6, "R3"), det("c1", 5, "R4", "advisory")]
    out = es.score(SCEN, dets)
    r3 = out["per_rule"]["R3"]["strict"]
    assert (r3["tp"], r3["fp"], r3["fn"]) == (1, 1, 0)  # turn 6 is a false positive
    assert (out["per_rule"]["R1"]["strict"]["tp"], out["per_rule"]["R5"]["strict"]["fn"]) == (1, 1)
    assert out["per_rule"]["R4"]["strict"]["fp"] == 1  # advisory counts as a positive prediction
    o = out["overall"]["strict"]
    assert (o["tp"], o["fp"], o["fn"]) == (2, 2, 2)  # fn: R5 turn 7 and R6 turn 3


def test_duplicate_detections_of_one_unit_count_once():
    out = es.score(SCEN, [det("c1", 5, "R3"), det("c1", 5, "R3"), det("c1", 5, "R3", "needs_review")])
    assert out["per_rule"]["R3"]["strict"]["tp"] == 1 and out["per_rule"]["R3"]["strict"]["fp"] == 0


def test_strict_versus_with_review():
    dets = [det("c2", 3, "R6", "needs_review"), det("c1", 7, "R5", "needs_review"), det("c3", 2, "R3", "needs_review")]
    out = es.score(SCEN, dets)
    r6 = out["per_rule"]["R6"]
    assert (r6["strict"]["tp"], r6["strict"]["fn"], r6["strict"]["r"]) == (0, 1, 0.0)
    assert (r6["with_review"]["tp"], r6["with_review"]["fn"], r6["with_review"]["r"]) == (1, 0, 1.0)
    assert out["per_rule"]["R5"]["with_review"]["tp"] == 1
    assert out["overall"]["needs_review"] == {"on_label": 2, "off_label": 1}
    assert out["overall"]["strict"]["fp"] == 0 and out["overall"]["with_review"]["fp"] == 1  # the c3 review item
    assert out["negatives"]["calls_with_false_alarm"] == 0 and out["negatives"]["calls_with_false_alarm_with_review"] == 1


def test_strongest_kind_wins_per_unit():
    k = es.unit_kinds([det("c1", 5, "R3", "needs_review"), det("c1", 5, "R3", "advisory"), det("c1", 5, "R3", "violation")])
    assert k == {("c1", 5, "R3"): "violation"}


def test_empty_cases():
    out = es.score([sc("n1"), sc("n2")], [])
    assert out["overall"]["strict"] == es.prf(0, 0, 0)
    assert out["negatives"] == {"calls": 2, "calls_with_false_alarm": 0, "false_alarm_units": 0,
                                "calls_with_false_alarm_with_review": 0}
    assert out["call_level"]["expected"] == 0
    none = es.score(SCEN, [])  # labels exist, nothing detected: recall 0, precision undefined
    o = none["overall"]["strict"]
    assert (o["tp"], o["fp"], o["fn"], o["p"], o["r"]) == (0, 0, 4, None, 0.0)


def test_hard_negative_false_alarm():
    out = es.score(SCEN, [det("c3", 4, "R3")])
    neg = out["negatives"]
    assert neg["calls"] == 1 and neg["calls_with_false_alarm"] == 1 and neg["false_alarm_units"] == 1
    c3 = next(c for c in out["per_call"] if c["call_id"] == "c3")
    assert c3["hard_negative"] and c3["false_alarms"] == [("c3", 4, "R3")]
    assert out["overall"]["strict"]["fp"] == 1


def test_g1_reported_apart():
    dets = [det("c1", 5, "R3"), det("c1", 2, "G1", "good_practice"), det("c1", 2, "G1", "good_practice"),
            det("c2", 4, "G1", "good_practice")]
    out = es.score(SCEN, dets)
    assert out["g1"] == {"findings": 3, "agent_turns_with_g1": 2}
    assert out["overall"]["strict"]["fp"] == 0 and "G1" not in out["per_rule"]


def test_call_level_recall():
    dets = [det("c1", 5, "R3"), det("c1", 6, "R3"), det("c2", 3, "R6", "needs_review")]
    out = es.score(SCEN, dets)
    assert out["call_level"] == {"expected": 4, "caught": 1, "caught_with_review": 2}  # c1: R1 R3 R5, c2: R6
    c1 = next(c for c in out["per_call"] if c["call_id"] == "c1")
    assert c1["caught_rules"] == ["R3"] and c1["expected_rules"] == ["R1", "R3", "R5"]


def test_subset_of_calls():
    dets = [det("c1", 5, "R3"), det("c2", 3, "R6")]
    out = es.score(SCEN, dets, calls=["c2"])
    assert out["n_calls"] == 1
    assert (out["overall"]["strict"]["tp"], out["overall"]["strict"]["fp"], out["overall"]["strict"]["fn"]) == (1, 0, 0)


def test_labels_hash_changes_with_labels():
    a = es.labels_hash(SCEN)
    assert a == es.labels_hash(list(reversed(SCEN)))
    assert a != es.labels_hash([sc("c1", [(1, "R1")]), *SCEN[1:]])
