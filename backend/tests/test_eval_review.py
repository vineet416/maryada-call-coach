"""'After human review of extras': hand-made runs and verdicts (no files, no model, no HTTP)."""
from app.evaluation import review_adjusted


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    return {"tp": tp, "fp": fp, "fn": fn, "p": p, "r": r, "f1": None}


def call(cid, fa, fa_review=None):
    return {"call_id": cid, "false_alarms": fa, "false_alarms_with_review": fa_review if fa_review is not None else fa}


RUN = {
    "all": {"per_call": [call("c01", [["c01", 3, "R3"], ["c01", 5, "R4"]]),
                         call("c02", [["c02", 3, "R3"], ["c02", 7, "R5"]], [["c02", 3, "R3"], ["c02", 7, "R5"], ["c02", 9, "R5"]])]},
}
RUN["all"]["overall"] = {"strict": prf(6, 4, 2), "with_review": prf(8, 5, 0)}
RUN["held_out"] = {"overall": {"strict": prf(3, 2, 1), "with_review": prf(4, 3, 0)}}
ITEMS = [
    {"call": "c01", "turn": 3, "rule": "R3", "verdict": "real"},
    {"call": "c01", "turn": 5, "rule": "R4", "verdict": "unsure"},
    {"call": "c02", "turn": 3, "rule": "R3", "verdict": "not_a_violation"},
    {"call": "c02", "turn": 7, "rule": "R5", "verdict": "unsure"},
    {"call": "c02", "turn": 9, "rule": "R5", "verdict": "not_a_violation"},
]


def test_real_counts_correct_unsure_is_a_range_and_recall_is_unchanged():
    s = review_adjusted(RUN, ["c02"], ITEMS)["all"]["strict"]
    assert (s["flags"], s["correct_original"]) == (10, 6)
    assert (s["extras_real"], s["extras_unsure"], s["extras_not_a_violation"]) == (1, 2, 1)
    assert (s["correct_low"], s["correct_high"]) == (7, 9)  # unsure all false, all correct
    assert s["precision_original"] == 0.6 and s["precision_low"] == 0.7 and s["precision_high"] == 0.9
    assert s["recall"] == 0.75  # 6 of 8 labelled units, as before


def test_with_review_view_uses_its_own_false_alarms():
    w = review_adjusted(RUN, ["c02"], ITEMS)["all"]["with_review"]
    assert w["flags"] == 13 and w["extras_not_a_violation"] == 2  # the review-only extra on c02 t9 counts here
    assert (w["correct_low"], w["correct_high"]) == (9, 11)
    assert w["recall"] == 1.0


def test_held_out_group_counts_only_its_calls():
    h = review_adjusted(RUN, ["c02"], ITEMS)["held_out"]["strict"]
    assert (h["extras_real"], h["extras_unsure"], h["extras_not_a_violation"]) == (0, 1, 1)
    assert (h["correct_low"], h["correct_high"], h["flags"]) == (3, 4, 5)


def test_no_verdicts_or_unknown_verdicts_give_none_and_a_wrong_unit_is_ignored():
    assert review_adjusted(RUN, [], []) is None
    assert review_adjusted(RUN, [], [{"call": "c01", "turn": 3, "rule": "R3", "verdict": "maybe"}]) is None
    s = review_adjusted(RUN, [], [{"call": "c99", "turn": 1, "rule": "R1", "verdict": "real"}])["all"]["strict"]
    assert s["extras_real"] == 0 and s["precision_low"] == s["precision_original"]
