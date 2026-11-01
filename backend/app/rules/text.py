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


# ---- script-tolerant matching: used ONLY for the R2 and R6 phrase lists (the other rules keep exact matching) ----
# A word is reduced to a rough consonant skeleton that is the same for its Roman and Devanagari spellings
# (record = रिकॉर्ड = "rkrd", zaroori = ज़रूरी = जरूरी = "jr"), so text mixing both scripts still matches.
_DEV = {**dict.fromkeys("कखक़ख़", "k"), **dict.fromkeys("गघग़", "g"), **dict.fromkeys("चछ", "C"), **dict.fromkeys("जझज़", "j"),
        **dict.fromkeys("टठतथ", "t"), **dict.fromkeys("डढदधड़ढ़", "d"), **dict.fromkeys("णन", "n"),
        **dict.fromkeys("पफफ़", "p"), **dict.fromkeys("बभ", "b"), "म": "m", "र": "r", "ल": "l", "ळ": "l",
        **dict.fromkeys("शषस", "s"), "ह": "h", "ं": "n", "ँ": "n", "ः": "h"}
_ASPIRABLE = set("kgCjtdpb")


def skeleton(word: str) -> str:
    """Consonant skeleton of one normalised word (vowels, y, w, v, nukta and halant dropped, aspiration folded)."""
    w = unicodedata.normalize("NFD", word).replace("़", "")  # NFD splits precomposed ज़ ड़ ...; the nukta is dropped
    w = w.replace("ch", "C").replace("sh", "s")
    out: list[str] = []
    for ch in w:
        c = _DEV.get(ch)
        if c is None:
            if "a" <= ch <= "z":
                c = {"c": "k", "q": "k", "x": "k", "z": "j", "f": "p"}.get(ch, ch)
                if c in "aeiouywv":
                    continue
                if c == "h" and out and out[-1] in _ASPIRABLE:
                    continue  # bh, kh, th ... -> b, k, t
            elif ch.isdigit() or ch == "C":
                c = ch
            else:
                continue  # Devanagari vowels and signs, halant, other marks
        if not out or out[-1] != c:
            out.append(c)
    return "".join(out)


def tolerant_words(words: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """(word, token_index) pairs as skeletons; words with no consonant are dropped (on both the phrase and text side)."""
    return [(s, i) for w, i in words if (s := skeleton(w))]


def tolerant_phrase(entry_variant: str) -> str:
    return " ".join(s for w in entry_variant.split() if (s := skeleton(w)))
