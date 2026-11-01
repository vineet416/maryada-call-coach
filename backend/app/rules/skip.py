"""Lexicon keyword guard for the short-segment skip (the existing prefilter lists only; no new phrases)."""
from functools import lru_cache

from ..config import settings
from .loader import load_rules
from .schemas import CallContext, Finding, Turn
from .text import find_phrase, split_variants, tokenize, words_of

# (rule, list name): abuse / threat (R3), legal terms (R5), third-party disclosure and shaming (R4), occasion (R6).
_LISTS = (("R3", "strong"), ("R3", "weak"), ("R5", "strong"), ("R5", "weak"),
          ("R4", "disclosure_triggers"), ("R4", "shaming_triggers"))


@lru_cache(maxsize=1)
def guard_keywords() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(agent-side keyword variants, sensitive-occasion variants), normalised."""
    rules = {r["id"]: r for r in load_rules()["rules"]}
    agent = [v for rid, key in _LISTS for e in rules[rid]["prefilter"].get(key, []) for v in split_variants(e)]
    occasion = [v for e in rules["R6"]["prefilter"]["borrower_context_triggers"] for v in split_variants(e)]
    return tuple(agent), tuple(occasion)


def _any(text: str, variants: tuple[str, ...]) -> bool:
    words = words_of(tokenize(text))
    return any(find_phrase(words, v) for v in variants)


def has_lexicon_keyword(ctx: CallContext, history: list[Turn], text: str) -> bool:
    """True when the text carries an abuse/threat/legal/third-party keyword or a sensitive-occasion keyword, or when
    the call already has a sensitive occasion (borrower_context, or an earlier borrower turn that mentions one)."""
    agent, occasion = guard_keywords()
    if _any(text, agent + occasion):
        return True
    if ctx.borrower_context:
        return True
    return any(t.speaker == "B" and _any(t.text, occasion) for t in history)


def should_skip(ctx: CallContext, history: list[Turn], text: str, fast: list[Finding]) -> bool:
    """Skip the LLM review of short agent text only when ALL hold: fewer words than SKIP_LLM_MAX_WORDS, the fast
    prefilter and gates found nothing (good practice does not count), and no lexicon / sensitive-occasion keyword
    (see has_lexicon_keyword). The caller logs a skip as skipped, never as a clean review."""
    return (len(text.split()) < settings.skip_llm_max_words
            and not any(f.kind != "good_practice" for f in fast)
            and not has_lexicon_keyword(ctx, history, text))
