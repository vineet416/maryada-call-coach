"""Zero-token audit: agent text units under N words across all calls (no LLM, no HTTP).

For each agent turn under N words, and for each sentence-prefix of a longer turn that is under N words (the live
pipeline reviews the text accumulated so far, so a first short STT segment looks like a short prefix), prints the turn,
word count, whether the fast prefilter flagged it, whether it carries a lexicon keyword (abuse / threat / legal /
third-party / sensitive occasion) and the rules the labels expect on the turn.
Usage: backend/.venv/Scripts/python.exe tools/short_segment_audit.py [max_words=8]
"""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.rules.engine import fast_findings
from app.rules.schemas import CallContext, Turn
from app.rules.skip import guard_keywords, has_lexicon_keyword


def load_calls() -> list[dict]:
    calls = []
    for p in sorted((ROOT / "content" / "scenarios").glob("*.yaml")):
        calls += yaml.safe_load(p.read_text(encoding="utf-8"))["scenarios"]
    return sorted(calls, key=lambda c: int(c["id"][1:]))


def prefixes(text: str) -> list[str]:
    """Cumulative sentence prefixes of a turn: 'A.', 'A. B.', ..."""
    parts = [p for p in re.split(r"(?<=[.?!।])\s+", text.strip()) if p]
    return [" ".join(parts[: i + 1]) for i in range(len(parts))]


def hero_segments(limit: int) -> None:
    """The hero call's real STT segments (recorded replay), accumulated per turn as the live pipeline sends them."""
    import json
    sc = next(c for c in load_calls() if c["id"] == "c06")
    ctx = CallContext(answered_by=sc["answered_by"], simulated_start_time=sc["time"])
    ev = json.loads((ROOT / "data/replay/c06.json").read_text(encoding="utf-8"))["events"]
    segs = [e["data"] for e in ev if e["type"] == "transcript.final"]
    hist: list[Turn] = []
    print("\nHero c06, real STT segments (cumulative text per agent segment):")
    print("turn seg words prefilter keyword turn_labels text")
    total = 0
    for i, t in enumerate(sc["turns"], 1):
        text = ""
        for sg in (x for x in segs if x["turn_idx"] == i):
            text = f"{text} {sg['text']}".strip()
            if t["s"] != "A" or not sg["text"]:
                continue
            total += 1
            n = len(text.split())
            if n < limit:
                fl = ",".join(sorted({f.rule_id for f in fast_findings(ctx, hist, i, text) if f.kind != "good_practice"})) or "-"
                kw = "yes" if has_lexicon_keyword(ctx, hist, text) else "no"
                exp = ",".join(r for r, _ in (t.get("L") or [])) or "-"
                print(f"{i:>4} {sg['segment_idx']:>3} {n:>5} {fl:9} {kw:7} {exp:11} {text}")
        hist.append(Turn(speaker=t["s"], text=t["t"]))
    print(f"hero agent segments in total: {total}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    guard_keywords()
    rows, n_turns, n_agent = [], 0, 0
    for sc in load_calls():
        ctx = CallContext(answered_by=sc["answered_by"], simulated_start_time=sc["time"])
        hist: list[Turn] = []
        for i, t in enumerate(sc["turns"], 1):
            if t["s"] == "A":
                n_agent += 1
                labels = t.get("L") or []
                exp = ",".join(r for r, _ in labels) or "-"
                units = [("turn", t["t"])] + ([("prefix", p) for p in prefixes(t["t"])[:-1]] if len(prefixes(t["t"])) > 1 else [])
                for kind, text in units:
                    n = len(text.split())
                    if n >= limit:
                        continue
                    flagged = ",".join(sorted({f.rule_id for f in fast_findings(ctx, hist, i, text) if f.kind != "good_practice"})) or "-"
                    kw = has_lexicon_keyword(ctx, hist, text)
                    inside = ",".join(r for r, ph in labels if ph.lower() in text.lower()) or "-"
                    rows.append((sc["id"], i, kind, n, flagged, "yes" if kw else "no", exp, inside, text))
            hist.append(Turn(speaker=t["s"], text=t["t"]))
            n_turns += 1
    print(f"calls={len(load_calls())} agent_turns={n_agent} units_under_{limit}_words={len(rows)}")
    print("call turn kind   words prefilter keyword turn_labels label_inside_unit  text")
    for r in rows:
        print(f"{r[0]:4} {r[1]:>4} {r[2]:6} {r[3]:>5} {r[4]:9} {r[5]:7} {r[6]:9} {r[7]:9} {r[8]}")
    risky = [r for r in rows if r[7] != "-"]  # the labelled phrase itself sits inside the short unit
    print(f"\nshort units that contain a labelled phrase: {len(risky)}")
    for r in risky:
        print("  ", r[:8], "prefilter-flagged" if r[4] != "-" else "NOT FLAGGED", "keyword-guarded" if r[5] == "yes" else "")
    whole = [r for r in rows if r[2] == "turn" and r[6] != "-"]
    print(f"whole agent turns under the limit that carry a turn label: {len(whole)} (R1 gate: {sum(1 for r in whole if r[6] == 'R1')})")
    hero_segments(limit)
    print(f"longest short unit holding a labelled phrase: {max((r[3] for r in risky), default=None)} words")


if __name__ == "__main__":
    main()
