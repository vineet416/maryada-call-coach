"""Time-to-flag statistics from recorded runs: pure functions on hand-made events."""
from app.evaluation import latency_stats, percentile


def ev(fid, phase, total, llm=0, kind="violation"):
    return {"type": "finding.detected", "data": {"id": fid, "phase": phase, "kind": kind,
                                                 "latency": {"total_ms": total, "llm_ms": llm}}}


def test_percentile_interpolates():
    assert percentile([], 50) is None
    assert percentile([5], 95) == 5
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([10, 20, 30, 40, 50], 95) == 48


def test_first_flag_counts_each_finding_once_and_skips_good_practice():
    runs = {"c1": [ev("a", "fast", 2000), ev("a", "deep", 4000, 1200), ev("b", "deep", 5000, 1400),
                   ev("g", "deep", 900, 800, "good_practice"), {"type": "transcript.final", "data": {}}]}
    rows = {r["label"]: r for r in latency_stats(runs)["rows"]}
    assert rows["First flag (either check)"]["n"] == 2 and rows["First flag (either check)"]["p50_ms"] == 3500
    assert rows["Fast phrase check"]["n"] == 1 and rows["Fast phrase check"]["p50_ms"] == 2000
    assert rows["Deep language check"]["n"] == 2 and rows["Deep language check"]["p95_ms"] == 4950
    assert rows["Language model step"]["n"] == 2


def test_same_id_in_two_calls_is_two_findings_and_empty_input():
    runs = {"c1": [ev("a", "fast", 1000)], "c2": [ev("a", "fast", 3000)]}
    assert latency_stats(runs)["rows"][0]["n"] == 2
    empty = latency_stats({})["rows"]
    assert all(r["n"] == 0 and r["p50_ms"] is None for r in empty)


def test_malformed_events_are_skipped_not_fatal():
    bad = [ev("a", ["fast"], 1000), {"type": "finding.detected", "data": "x"}, "junk", {"type": "finding.detected", "data": {"latency": 5}},
           ev("b", "deep", 2000, 900)]
    rows = {r["label"]: r for r in latency_stats({"c1": bad})["rows"]}
    assert rows["First flag (either check)"]["n"] == 1 and rows["Deep language check"]["n"] == 1
