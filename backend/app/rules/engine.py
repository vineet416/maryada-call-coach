"""Engine: merge prefilter + LLM findings, thresholds, alignment, stable ids (docs/03 §3.4-3.6, docs/13 §4)."""
import hashlib

from pydantic import ValidationError

from .align import align_quote
from .loader import load_rules
from .prefilter import gate_findings, good_practice, prefilter
from .schemas import CallContext, Finding, LlmOut, Turn

VIOLATION_MIN, REVIEW_MIN = 0.75, 0.45
WEAK_CAP = 0.74  # weak alignment (whole-sentence fallback) must stay needs_review
_RANK = {"good_practice": 0, "advisory": 1, "needs_review": 2, "violation": 3}


def kind_for(rule_id: str, confidence: float) -> str | None:
    """Threshold mapping. None = dropped. R2/R6 never exceed their default kind."""
    if confidence < REVIEW_MIN:
        return None
    kind = "violation" if confidence >= VIOLATION_MIN else "needs_review"
    default = next(r["kind_default"] for r in load_rules()["rules"] if r["id"] == rule_id)
    return kind if _RANK[kind] <= _RANK[default] else default


def stable_id(turn_idx: int, rule_id: str, quote: str) -> str:
    return hashlib.sha1(f"{turn_idx}|{rule_id}|{quote}".encode()).hexdigest()[:12]


def parse_llm(raw: str) -> LlmOut | None:
    """Pydantic validation of the LLM JSON; None on any failure (caller retries / degrades)."""
    try:
        return LlmOut.model_validate_json(raw)
    except (ValidationError, ValueError):
        return None


def llm_to_findings(out: LlmOut, turn_idx: int, text: str) -> list[Finding]:
    res = []
    for lf in out.findings:
        rng, _ratio, sentence = align_quote(text, lf.quote)
        conf = lf.confidence if not sentence else min(lf.confidence, WEAK_CAP)  # weak alignment -> needs_review
        res.append(Finding(turn_idx=turn_idx, rule_id=lf.rule_id, confidence=conf, quote=lf.quote,
                           token_range=rng, reason=lf.reason, rewrite=lf.rewrite, source="llm", phase="deep",
                           weak_alignment=sentence))
    return res


def merge(items: list[Finding]) -> list[Finding]:
    """Same rule + overlapping range -> one finding, source 'both', confidence = max + 0.05 (cap 1)."""
    out: list[Finding] = []
    for f in sorted(items, key=lambda x: (x.rule_id, x.token_range[0])):
        prev = next((p for p in out if p.rule_id == f.rule_id and f.token_range[0] < p.token_range[1]
                     and p.token_range[0] < f.token_range[1]), None)
        if prev is None:
            out.append(f.model_copy())
            continue
        if {prev.source, f.source} == {"prefilter", "llm"}:
            prev.source = "both"
            prev.confidence = min(1.0, max(prev.confidence, f.confidence) + 0.05)
        else:
            prev.confidence = max(prev.confidence, f.confidence)
        prev.weak_alignment = prev.weak_alignment and f.weak_alignment  # an exact-phrase hit keeps its strength
        if prev.weak_alignment:
            prev.confidence = min(prev.confidence, WEAK_CAP)
        prev.token_range = (min(prev.token_range[0], f.token_range[0]), max(prev.token_range[1], f.token_range[1]))
        prev.reason = prev.reason or f.reason
        prev.rewrite = prev.rewrite or f.rewrite
        if f.source == "llm":
            prev.quote = prev.quote or f.quote
    return out


def finalize(items: list[Finding], turn_idx: int, text: str) -> list[Finding]:
    """Apply thresholds, drop <0.45, fill ids; keep order by token start."""
    out = []
    for f in merge(items):
        if f.kind != "good_practice":
            kind = kind_for(f.rule_id, f.confidence)
            if kind is None:
                continue
            f.kind = kind
        f.turn_idx = turn_idx
        f.id = stable_id(turn_idx, f.rule_id, f.quote or "*")
        out.append(f)
    return sorted(out, key=lambda x: x.token_range[0])


def fast_findings(ctx: CallContext, history: list[Turn], turn_idx: int, text: str) -> list[Finding]:
    """Fast phase: gates + prefilter + good practice (no LLM)."""
    agent_texts = [t.text for t in history if t.speaker == "A"] + [text]
    agent_no = len(agent_texts)
    items = gate_findings(ctx, turn_idx, agent_no, text, agent_texts)
    items += prefilter(ctx, history, turn_idx, text) + good_practice(text, turn_idx)
    return finalize(items, turn_idx, text)


def deep_findings(ctx: CallContext, fast: list[Finding], llm: LlmOut | None, turn_idx: int, text: str) -> list[Finding]:
    """Deep phase: merge the LLM result into the fast findings. llm=None -> fast findings unchanged."""
    if llm is None:
        return fast
    from_llm = llm_to_findings(llm, turn_idx, text)
    if ctx.answered_by == "borrower":  # R4 gate applies to the LLM too
        from_llm = [f for f in from_llm if f.rule_id != "R4"]
    items = [f for f in fast if f.kind != "good_practice"] + from_llm
    merged = finalize(items, turn_idx, text)
    for g in llm.good_practice:
        rng, _, sentence = align_quote(text, g.quote)
        if not sentence:
            merged.append(Finding(turn_idx=turn_idx, rule_id="G1", kind="good_practice", confidence=1.0,
                                  quote=g.quote, token_range=rng, reason=g.note, source="llm", phase="deep",
                                  id=stable_id(turn_idx, "G1", g.quote)))
    return merged
