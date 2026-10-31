"""Pure-function tests for the rule engine: gates, alignment, merge, thresholds, risk, JSON failure path."""
import pytest
import yaml
from app.config import settings
from app.rules import risk
from app.rules.align import align_quote
from app.rules.engine import fast_findings, kind_for, merge, parse_llm
from app.rules.prefilter import prefilter, r1_violation, r2_missing
from app.rules.schemas import CallContext, Finding, Turn


@pytest.mark.parametrize("t,bad", [("07:59", True), ("08:00", False), ("19:00", False), ("19:01", True), ("12:30", False)])
def test_r1_boundaries(t, bad):
    assert r1_violation(t) is bad


def test_r2_lookback_uses_first_two_agent_turns():
    ok = ["Namaste, main Rohit bol raha hoon Tarang Finserv se.", "Yeh call record ho rahi hai."]
    assert not r2_missing(ok)
    assert r2_missing(["Namaste, Rohit bol raha hoon Tarang Finserv se.", "EMI kab bharenge?"])
    assert r2_missing(["Hello, EMI pending hai.", "Kab tak payment hoga?"])


def test_r2_gate_fires_on_second_agent_turn_only():
    ctx = CallContext()
    hist = [Turn(speaker="A", text="Hello, EMI pending hai."), Turn(speaker="B", text="Haan.")]
    assert not [f for f in fast_findings(ctx, [], 1, "Hello, EMI pending hai.") if f.rule_id == "R2"]
    got = fast_findings(ctx, hist, 3, "Kab tak payment karenge?")
    assert [f.rule_id for f in got if f.kind == "advisory"] == ["R2"]


def test_r4_gate_only_when_not_borrower():
    text = "Unki EMI pending hai aur default ho gaya hai."
    assert not [f for f in prefilter(CallContext(answered_by="borrower"), [], 1, text) if f.rule_id == "R4"]
    assert [f for f in prefilter(CallContext(answered_by="spouse"), [], 1, text) if f.rule_id == "R4"]


def test_align_exact_partial_and_fallback():
    text = "Dekho, aaj shaam tak payment nahi aaya to police ko bhejunga aapke ghar. Samjhi?"
    rng, ratio, sentence = align_quote(text, "police ko bhejunga aapke ghar")
    assert ratio == 1.0 and not sentence and text.split()[rng[0]:rng[1]][0] == "police"
    rng, ratio, sentence = align_quote(text, "police ko bhejenge aapke ghar")  # partial
    assert not sentence and 0.6 <= ratio < 1.0
    rng, ratio, sentence = align_quote(text, "bilkul alag baat hai yeh")
    assert sentence and rng[0] <= rng[1]


def test_align_devanagari_roman_mix():
    text = "Aapke mohalle में सबको बता दूंगा ki aap defaulter ho."
    rng, ratio, sentence = align_quote(text, "mohalle में सबको बता दूंगा")
    assert ratio == 1.0 and not sentence and rng == (1, 6)


def test_threshold_mapping():
    assert kind_for("R3", 0.9) == "violation" and kind_for("R3", 0.75) == "violation"
    assert kind_for("R3", 0.6) == "needs_review" and kind_for("R3", 0.45) == "needs_review"
    assert kind_for("R3", 0.44) is None
    assert kind_for("R2", 0.95) == "advisory" and kind_for("R6", 0.95) == "needs_review"


def test_merge_prefilter_and_llm():
    a = Finding(rule_id="R5", confidence=0.9, token_range=(2, 5), source="prefilter")
    b = Finding(rule_id="R5", confidence=0.8, token_range=(3, 8), source="llm", reason="x")
    c = Finding(rule_id="R3", confidence=0.9, token_range=(3, 8), source="llm")
    out = merge([a, b, c])
    r5 = next(f for f in out if f.rule_id == "R5")
    assert len(out) == 2 and r5.source == "both" and r5.confidence == pytest.approx(0.95) and r5.token_range == (2, 8)
    assert merge([a.model_copy(update={"confidence": 0.98}), b.model_copy(update={"confidence": 0.98})])[0].confidence == 1.0


def test_llm_json_validation_failure_path():
    assert parse_llm("not json") is None
    assert parse_llm('{"findings":[{"rule_id":"R9","confidence":0.9,"quote":"x"}]}') is None
    assert parse_llm('{"findings":[{"rule_id":"R3","confidence":1.7,"quote":"x"}]}') is None
    assert parse_llm('{"findings":[],"good_practice":[]}') is not None


def _f(rule, kind):
    return Finding(rule_id=rule, kind=kind, confidence=0.9)


def test_risk_increments_decay_clamp_bands():
    assert risk.update(0, [_f("R3", "violation"), _f("R5", "violation")]).score == 65
    assert risk.update(0, [_f("R5", "violation"), _f("R5", "violation")]).delta == 35  # same rule counts once
    assert risk.update(0, [_f("R3", "needs_review")]).delta == 6
    assert risk.update(0, [_f("R2", "advisory")]).delta == 8 and risk.update(0, [_f("R6", "needs_review")]).delta == 10
    assert risk.update(0, [_f("G1", "good_practice")]).score == 0
    u = risk.update(65, [])
    assert u.score == 55 and u.delta == -10 and u.reason_rule_id is None
    assert risk.update(90, [_f("R4", "violation")]).score == 100
    assert [risk.band(s) for s in (29, 30, 60, 61)] == ["low", "medium", "medium", "high"]
    assert risk.update(0, [_f("R3", "violation"), _f("R5", "violation")]).reason_rule_id == "R5"


def _call(cid):
    for p in sorted(settings.content_dir.glob("scenarios/*.yaml")):
        for s in yaml.safe_load(p.read_text(encoding="utf-8"))["scenarios"]:
            if s["id"] == cid:
                return s


def test_hero_call_flags_r5_r3_r5_on_turn_7_and_nothing_else():
    sc = _call("c06")
    assert len(sc["turns"]) == 11
    ctx = CallContext(answered_by=sc["answered_by"], simulated_start_time=sc["time"])
    hist, score, peak = [], 0, 0
    for i, t in enumerate(sc["turns"], 1):
        if t["s"] == "A":
            found = fast_findings(ctx, hist, i, t["t"])
            bad = [f.rule_id for f in found if f.kind != "good_practice"]
            assert bad == (["R5", "R3", "R5"] if i == 7 else []), f"turn {i}: {bad}"
            score = risk.update(score, found).score
            peak = max(peak, score)
        hist.append(Turn(speaker=t["s"], text=t["t"]))
    assert peak == 65 and risk.band(peak) == "high"
