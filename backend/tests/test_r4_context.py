"""R4 is judged only when the call was answered by a spouse or a neighbour; borrower and "unknown" (Speak live, not chosen yet) are not."""
import pytest
from app.rules.engine import deep_findings, fast_findings
from app.rules.schemas import CallContext, LlmFinding, LlmOut

TEXT = "Aapke husband ne loan liya tha, EMI pending hai, 18000 rupaye baaki hain."


def r4(answered_by):
    ctx = CallContext(answered_by=answered_by, simulated_start_time="12:00")
    return [f for f in fast_findings(ctx, [], 5, TEXT) if f.rule_id == "R4"]


@pytest.mark.parametrize("who,judged", [("unknown", False), ("borrower", False), ("spouse", True), ("neighbour", True)])
def test_prefilter_r4_gate(who, judged):
    assert bool(r4(who)) is judged


@pytest.mark.parametrize("who,judged", [("unknown", False), ("borrower", False), ("spouse", True), ("neighbour", True)])
def test_llm_r4_gate(who, judged):
    ctx = CallContext(answered_by=who, simulated_start_time="12:00")
    llm = LlmOut(findings=[LlmFinding(rule_id="R4", confidence=0.95, quote="EMI pending hai")])
    out = deep_findings(ctx, [], llm, 5, TEXT)
    assert any(f.rule_id == "R4" for f in out) is judged


def test_recorded_cases_keep_their_value():
    assert CallContext().answered_by == "borrower"
