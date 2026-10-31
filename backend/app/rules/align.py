"""Quote -> token alignment (docs/03 §3.5)."""
from difflib import SequenceMatcher

from .text import norm_tokens, normalize, tokenize

MIN_RATIO = 0.6
_SENTENCE_END = (".", "?", "!", "।")


def align_quote(text: str, quote: str) -> tuple[tuple[int, int], float, bool]:
    """Return (token_range [start, end), match ratio, whole_sentence_fallback).

    Exact substring is mapped by character offsets. Otherwise the best contiguous window of
    normalised tokens is chosen with difflib; below MIN_RATIO the whole sentence around the best
    window is returned and the caller marks the finding needs_review.
    """
    toks = tokenize(text)
    if not toks or not quote.strip():
        return (0, len(toks)), 0.0, True
    pos = text.find(quote)
    if pos >= 0:
        end = pos + len(quote)
        idx = [i for i, t in enumerate(toks) if t[1] < end and t[2] > pos]
        if idx:
            return (idx[0], idx[-1] + 1), 1.0, False
    nt = norm_tokens(toks)
    q = [w for w in normalize(quote).split()]
    if not q:
        return (0, len(toks)), 0.0, True
    best = (0.0, 0, 1)
    for length in sorted({max(1, len(q) - 1), len(q), len(q) + 1}):
        for s in range(max(1, len(nt) - length + 1)):
            window = " ".join(nt[s:s + length]).split()
            r = SequenceMatcher(None, q, window).ratio()
            if r > best[0] + 1e-9:
                best = (r, s, min(len(nt), s + length))
    ratio, s, e = best
    if ratio >= MIN_RATIO:
        return (s, e), ratio, False
    start = s
    while start > 0 and not toks[start - 1][0].endswith(_SENTENCE_END):
        start -= 1
    end = max(e, s + 1)
    while end < len(toks) and not toks[end - 1][0].endswith(_SENTENCE_END):
        end += 1
    return (start, end), ratio, True
