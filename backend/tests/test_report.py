"""Call report builder: risk series, counts, hidden rewording, first flag, early-to-deep replacement (pure, no server)."""
import json

import pytest
from app.config import settings
from app.report import build_report
from app.rules.loader import load_rules

RULES = [{"id": "R1", "title": "Calling hours", "why": "Hours matter."}, {"id": "R2", "title": "Identify", "why": ""},
         {"id": "R3", "title": "Abuse", "why": "Dignity.\n"}, {"id": "G1", "title": "Good practice", "why": "x"}]
META = {"id": "cX", "title": "A call", "date": "2026-10-01", "time": "11:00", "duration_ms": 60000, "turn_offsets": {1: 300, 2: 5000}}


def ev(t, typ, **data):
    return {"seq": 0, "type": typ, "t_ms": t, "data": data}


def finding(fid, rule, kind="violation", turn=1, rewrite="Say it kindly.", source="llm", rng=(0, 3), quote="q"):
    return {"id": fid, "turn_idx": turn, "rule_id": rule, "kind": kind, "confidence": 0.9, "quote": quote, "token_range": list(rng), "reason": "r",
                "rewrite": rewrite, "source": source, "rbi_ref": ""}


def build(events):
    return build_report(events, META, RULES, "replay")


def test_risk_series_follows_risk_updates_in_order():
    r = build([ev(10, "risk.update", score=0, delta=0, band="low", reason_rule_id=None),
               ev(20, "risk.update", score=65, delta=65, band="high", reason_rule_id="R3"),
               ev(30, "risk.update", score=55, delta=-10, band="high", reason_rule_id=None)])
    assert [(x["t_ms"], x["score"]) for x in r["risk"]] == [(10, 0), (20, 65), (30, 55)]
    assert r["kpis"]["peak_risk"] == 65 and r["kpis"]["peak_band"] == "high"


def test_no_risk_updates_gives_a_zero_peak_in_the_low_band():
    r = build([])
    assert r["risk"] == [] and r["kpis"]["peak_risk"] == 0 and r["kpis"]["peak_band"] == "low"
    assert r["kpis"]["first_flag_ms"] is None and r["by_rule"] == [] and r["coaching"] == [] and r["good"] == []


def test_counts_split_findings_from_good_practice_and_group_by_rule():
    r = build([ev(100, "finding.detected", **finding("a", "R3", turn=1)),
               ev(200, "finding.detected", **finding("b", "R3", turn=2, kind="needs_review")),
               ev(300, "finding.detected", **finding("c", "R2", kind="advisory", rewrite="")),
               ev(400, "finding.detected", **finding("d", "G1", kind="good_practice", rewrite=""))])
    assert r["kpis"]["findings_count"] == 3 and r["kpis"]["good_count"] == 1
    assert [(x["rule_id"], x["count"], x["title"]) for x in r["by_rule"]] == [("R3", 2, "Abuse"), ("R2", 1, "Identify")]
    assert r["by_rule"][0]["kind"] == "violation"  # the strongest kind labels the row
    assert r["good"][0]["finding"]["id"] == "d"


def test_first_flag_is_the_earliest_flag_not_good_practice():
    r = build([ev(50, "finding.detected", **finding("g", "G1", kind="good_practice", rewrite="")),
               ev(900, "finding.detected", **finding("b", "R3")), ev(700, "finding.detected", **finding("a", "R3", turn=2))])
    assert r["kpis"]["first_flag_ms"] == 700
    assert [f["t_ms"] for f in r["flags"]] == [700, 900]


def test_an_early_finding_is_replaced_by_its_deep_version_and_keeps_its_first_time():
    early = finding("a", "R3", kind="needs_review", rewrite="", source="prefilter")
    deep = finding("a", "R3", kind="violation", rewrite="Better words.", source="both")
    r = build([ev(100, "finding.detected", **early), ev(900, "finding.detected", **deep)])
    assert r["kpis"]["findings_count"] == 1 and r["flags"][0]["t_ms"] == 100
    assert r["coaching"][0]["finding"]["kind"] == "violation" and r["coaching"][0]["rewrite"] == "Better words."


@pytest.mark.parametrize("rule,source,rewrite,shown", [
    ("R1", "prefilter", "", False), ("R1", "llm", "Call after 8 am.", False), ("R2", "prefilter", "Introduce yourself.", False),
    ("R3", "prefilter", "Soft words.", False), ("R3", "llm", "Soft words.", True), ("R3", "both", "Soft words.", True),
    ("R3", "llm", "  ", False)])
def test_rewording_block_is_hidden_unless_it_exists(rule, source, rewrite, shown):
    r = build([ev(1, "finding.detected", **finding("a", rule, source=source, rewrite=rewrite))])
    assert (r["coaching"][0]["rewrite"] is not None) is shown


def test_coach_line_comes_only_from_the_nudge_of_that_finding():
    r = build([ev(1, "finding.detected", **finding("a", "R3")), ev(2, "finding.detected", **finding("b", "R3", turn=2)),
               ev(3, "coach.nudge", finding_id="a", rule_id="R3", text="Please stay calm.", audio_url="x")])
    assert [c["coach_line"] for c in r["coaching"]] == ["Please stay calm.", None]


def test_why_it_matters_is_the_rulebook_text_and_missing_when_empty():
    r = build([ev(1, "finding.detected", **finding("a", "R3")), ev(2, "finding.detected", **finding("b", "R2", kind="advisory", rewrite=""))])
    assert [c["why"] for c in r["coaching"]] == ["Dignity.", None] and r["coaching"][0]["rule_title"] == "Abuse"


def test_transcript_keeps_turn_order_offsets_and_ignores_a_repeated_segment():
    seg = [{"i": 0, "w": "Hello", "lang": "en"}, {"i": 1, "w": "ji", "lang": "hi"}]
    r = build([ev(1, "turn.started", turn_idx=2, speaker="borrower", duration_ms=900),
               ev(2, "turn.started", turn_idx=1, speaker="agent", duration_ms=800),
               ev(3, "transcript.final", turn_idx=1, tokens=seg), ev(4, "transcript.final", turn_idx=1, tokens=seg)])
    assert [(t["idx"], t["offset_ms"], len(t["tokens"])) for t in r["turns"]] == [(1, 300, 2), (2, 5000, 0)]


def test_band_edges_come_from_the_risk_module():
    assert build([])["bands"] == {"medium_from": 30, "high_from": 61}


# ---- the shipped recordings ----
def recorded(sid):
    return json.loads((settings.data_dir / "replay" / f"{sid}.json").read_text(encoding="utf-8"))["events"]


@pytest.mark.parametrize("sid", sorted(p.stem for p in (settings.data_dir / "replay").glob("c*.json")))
def test_report_totals_match_the_session_summary_of_the_recording(sid):
    events = recorded(sid)
    summary = next(e for e in events if e["type"] == "session.ended")["data"]["summary"]
    r = build_report(events, {**META, "id": sid}, load_rules()["rules"], "replay")
    assert r["kpis"]["findings_count"] == summary["findings_count"]
    assert r["kpis"]["peak_risk"] == summary["risk_peak"]
    assert {x["rule_id"]: x["count"] for x in r["by_rule"]} == summary["by_rule"]
    assert all(c["rewrite"] is None for c in r["coaching"] if c["finding"]["rule_id"] in ("R1", "R2"))
