"""Text helpers: normalisation, tokenising and phrase matching (Roman + Devanagari)."""
import re
import unicodedata

_TOKEN = re.compile(r"\S+")


def normalize_word(s: str) -> list[str]:
    """Lowercase, replace punctuation by spaces, return the remaining words (letters, digits, marks kept)."""
    out = []
    for ch in unicodedata.normalize("NFC", s).lower():
        out.append(ch if unicodedata.category(ch)[0] in "LNM" else " ")
    return "".join(out).split()


def normalize(s: str) -> str:
    return " ".join(normalize_word(s))


def tokenize(text: str) -> list[tuple[str, int, int]]:
    """Whitespace tokens with char offsets; punctuation stays on the token."""
    return [(m.group(), m.start(), m.end()) for m in _TOKEN.finditer(text)]


def norm_tokens(tokens: list[tuple[str, int, int]]) -> list[str]:
    """One normalised string per token (may be empty for pure punctuation)."""
    return [normalize(t[0]) for t in tokens]


def split_variants(entry: str) -> list[str]:
    """'roman | devanagari' -> normalised variants."""
    return [normalize(p) for p in entry.split("|") if normalize(p)]


def find_phrase(words: list[tuple[str, int]], phrase: str) -> list[tuple[int, int]]:
    """Find a normalised phrase in (word, token_index) pairs.

    All words must match exactly, except the last one, which may be a prefix when it has >= 4 letters
    (so the stem 'police ko bhej' matches 'police ko bhejunga'). Returns token ranges [start, end).
    """
    pw = phrase.split()
    hits = []
    for i in range(len(words) - len(pw) + 1):
        ok = True
        for j, p in enumerate(pw):
            w = words[i + j][0]
            last = j == len(pw) - 1
            if not (w == p or (last and len(p) >= 4 and w.startswith(p))):
                ok = False
                break
        if ok:
            hits.append((words[i][1], words[i + len(pw) - 1][1] + 1))
    return hits


def words_of(tokens: list[tuple[str, int, int]]) -> list[tuple[str, int]]:
    """Flatten tokens to (normalised word, token_index)."""
    return [(w, i) for i, t in enumerate(tokens) for w in normalize_word(t[0])]
