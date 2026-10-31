"""Deterministic prefilter: phrase hits and the R1/R2/R4 gates (docs/03 §3.1-3.2)."""
from typing import Any

from .loader import load_rules
from .schemas import CallContext, Finding, Turn
from .text import find_phrase, split_variants, tokenize, words_of

STRONG, WEAK = 0.9, 0.6
DAY_START, DAY_END = 8 * 60, 19 * 60  # 08:00 .. 19:00 inclusive


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def r1_violation(start_time: str) -> bool:
    """True when the call starts before 08:00 or after 19:00 (08:00 and 19:00 are allowed)."""
    return not (DAY_START <= _minutes(start_time) <= DAY_END)


def _hits(words: list[tuple[str, int]], entries: list[str]) -> list[tuple[int, int, str]]:
    out = []
    for entry in entries:
        for variant in split_variants(entry):
            for s, e in find_phrase(words, variant):
                out.append((s, e, variant))
    return out


def _any(words: list[tuple[str, int]], entries: list[str]) -> bool:
    return bool(_hits(words, entries))


def r2_missing(agent_turns: list[str]) -> bool:
    """Look-back over the first two agent turns: name + lender AND recording notice must both appear."""
    pf = load_rules_by_id()["R2"]["prefilter"]
    words = [w for t in agent_turns[:2] for w in words_of(tokenize(t))]
    ident = _any(words, pf["identification_patterns"])
    rec = _any(words, pf["recording_patterns"])
    return not (ident and rec)


def load_rules_by_id() -> dict[str, dict[str, Any]]:
    return {r["id"]: r for r in load_rules()["rules"]}


def _make(turn_idx: int, rule_id: str, conf: float, text: str, toks, s: int, e: int, kind: str = "violation") -> Finding:
    return Finding(turn_idx=turn_idx, rule_id=rule_id, kind=kind, confidence=conf,
                   quote=text[toks[s][1]:toks[e - 1][2]], token_range=(s, e), source="prefilter")


def prefilter(ctx: CallContext, history: list[Turn], turn_idx: int, text: str) -> list[Finding]:
    """Phrase candidates for one agent turn. `history` = all previous turns (for R6 context)."""
    rules = load_rules_by_id()
    toks = tokenize(text)
    words = words_of(toks)
    out: list[Finding] = []
    for rid in ("R3", "R5"):
        pf = rules[rid]["prefilter"]
        for key, conf in (("strong", STRONG), ("weak", WEAK)):
            for s, e, _ in _hits(words, pf.get(key, [])):
                out.append(_make(turn_idx, rid, conf, text, toks, s, e))
    if ctx.answered_by != "borrower":  # R4 gate
        pf = rules["R4"]["prefilter"]
        for key in ("disclosure_triggers", "shaming_triggers"):
            for s, e, v in _hits(words, pf.get(key, [])):
                out.append(_make(turn_idx, "R4", STRONG if len(v.split()) > 1 else WEAK, text, toks, s, e))
    pf = rules["R6"]["prefilter"]
    borrower_words = [w for t in history if t.speaker == "B" for w in words_of(tokenize(t.text))]
    if _any(borrower_words, pf["borrower_context_triggers"]) or ctx.borrower_context:
        for s, e, _ in _hits(words, pf["agent_pressing_patterns"]):
            out.append(_make(turn_idx, "R6", STRONG, text, toks, s, e, "needs_review"))
    return _merge_same_rule(out)


def good_practice(text: str, turn_idx: int) -> list[Finding]:
    pf = load_rules_by_id()["G1"]["prefilter"]
    toks = tokenize(text)
    return [_make(turn_idx, "G1", 1.0, text, toks, s, e, "good_practice")
            for s, e, _ in _hits(words_of(toks), pf["good_practice_patterns"])]


def _merge_same_rule(items: list[Finding]) -> list[Finding]:
    """Union overlapping hits of the same rule (e.g. two R3 phrases covering the same words)."""
    out: list[Finding] = []
    for f in sorted(items, key=lambda x: (x.rule_id, x.token_range[0])):
        prev = out[-1] if out else None
        if prev and prev.rule_id == f.rule_id and f.token_range[0] < prev.token_range[1]:
            prev.token_range = (prev.token_range[0], max(prev.token_range[1], f.token_range[1]))
            prev.confidence = max(prev.confidence, f.confidence)
        else:
            out.append(f.model_copy())
    return out


def gate_findings(ctx: CallContext, turn_idx: int, agent_turn_no: int, text: str, agent_turns: list[str]) -> list[Finding]:
    """R1 on the first agent turn, R2 on the second. Whole-turn findings ('*')."""
    n = len(tokenize(text))
    out: list[Finding] = []
    if agent_turn_no == 1 and r1_violation(ctx.simulated_start_time):
        out.append(Finding(turn_idx=turn_idx, rule_id="R1", kind="violation", confidence=1.0,
                           token_range=(0, n), source="gate"))
    if agent_turn_no == 2 and r2_missing(agent_turns):
        out.append(Finding(turn_idx=turn_idx, rule_id="R2", kind="advisory", confidence=1.0,
                           token_range=(0, n), source="gate"))
    return out
