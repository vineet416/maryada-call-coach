"""Validate the sample-call scripts in content/scenarios against the previous version.

Usage:  python tools/validate_scripts.py [--base main] [--cost] [files...]

Errors make the exit code 1; warnings (gender and sentence-count heuristics) are listed but do not.
The baseline is the same file at a git ref (default: main); it fixes labelled-turn counts, rule ids and metadata.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"
MAX_CHARS, MAX_TURNS, MIN_TURNS, MAX_FEMALE = 600, 11, 6, 2
RS_PER_1000_CHARS = 2.9  # docs/11: about 28,000 characters is about Rs 80
UNCHANGED = ["id", "agent", "date", "time", "answered_by", "borrower", "third_party", "facts", "hero", "hard_negative"]

MARATHI_WORDS = {
    "aahe", "aahet", "aahes", "bolto", "bolte", "bolat", "kaay", "kay", "zhala", "zhale", "mala", "mi", "sangte",
    "sangto", "vaait", "vatta", "gele", "padla", "bayko", "aai", "vadilanche", "sathi", "kuthe", "tumhi", "amhi",
    "nidhan", "zhal", "ho", "mhanje", "pahije", "nako", "nahich", "kasa", "kashi",
}
MARATHI_WORDS -= {"ho", "nidhan"}  # "ho" is a Hindi word in "ho gaya"; "nidhan" is a Hindi word, kept in the R6 triggers
MARATHI_CHARS = "ळ"  # Devanagari LLA, used by Marathi only

# first-person verb endings that give the speaker's gender away (heuristic)
MALE_FIRST = re.compile(
    r"\b(raha hoon|sakta hoon|chahta hoon|leta hoon|deta hoon|karta hoon|karunga|dunga|bhejunga|jaunga|"
    r"bataunga|dekhunga|lunga|paunga|samajh gaya|ruk gaya)\b", re.I)
FEMALE_FIRST = re.compile(
    r"\b(rahi hoon|sakti hoon|chahti hoon|leti hoon|deti hoon|karti hoon|karungi|dungi|bhejungi|jaungi|"
    r"bataungi|dekhungi|lungi|paungi|samajh gayi|ruk gayi)\b", re.I)

AGENT_GENDER = {}
for a in yaml.safe_load((CONTENT / "agents.yaml").read_text(encoding="utf-8"))["agents"]:
    AGENT_GENDER[a["id"]] = a["gender"]
BORROWER_GENDER = {"m1": "M", "m2": "M", "f": "F"}
THIRD_GENDER = {"spouse_f": "F", "neighbour_m": "M"}


def genders(sc: dict) -> dict[str, str]:
    g = {"A": AGENT_GENDER[sc["agent"]], "B": BORROWER_GENDER[sc["borrower"]["voice"]]}
    if sc.get("third_party"):
        g["T"] = THIRD_GENDER[sc["third_party"]["voice"]]
    return g


def load(text: str) -> dict[str, dict]:
    return {s["id"]: s for s in yaml.safe_load(text)["scenarios"]}


def baseline(ref: str, rel: str) -> dict[str, dict]:
    out = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=ROOT, capture_output=True, check=True)
    return load(out.stdout.decode("utf-8"))


def labelled(sc: dict) -> list[tuple[int, list[str]]]:
    return [(i, [lab[0] for lab in t["L"]]) for i, t in enumerate(sc["turns"]) if t.get("L")]


def sentences(text: str) -> int:
    return len([p for p in re.split(r"[.?!।]+", text) if p.strip(" .…—-")])


def check_scenario(sc: dict, old: dict | None, errs: list[str], warns: list[str]) -> None:
    cid = sc["id"]
    turns = sc["turns"]
    g = genders(sc)
    err = lambda m: errs.append(f"{cid}: {m}")  # noqa: E731
    warn = lambda m: warns.append(f"{cid}: {m}")  # noqa: E731

    if len(turns) > MAX_TURNS:
        err(f"{len(turns)} turns (max {MAX_TURNS})")
    if len(turns) < MIN_TURNS:
        warn(f"only {len(turns)} turns (target {MIN_TURNS}-{MAX_TURNS})")
    if sum(1 for s in g.values() if s == "F") > MAX_FEMALE:
        err("more than two female speakers (needs a third female voice)")
    if {t["s"] for t in turns} - set(g):
        err("a turn uses a speaker the call does not have")

    for i, t in enumerate(turns, 1):
        for key in ("t", "td"):
            if not t.get(key, "").strip():
                err(f"turn {i} has no {key}")
        if len(t.get("t", "")) > MAX_CHARS or len(t.get("td", "")) > MAX_CHARS:
            err(f"turn {i} is over {MAX_CHARS} characters")
        text = t.get("t", "")
        words = set(re.findall(r"[a-z]+", text.lower()))
        bad = words & MARATHI_WORDS
        if bad or any(ch in text + t.get("td", "") for ch in MARATHI_CHARS):
            err(f"turn {i} has Marathi words {sorted(bad)}")
        if sentences(text) != sentences(t.get("td", "")):
            warn(f"turn {i}: t and td have different sentence counts")
        gender = g.get(t["s"])
        if gender == "F" and MALE_FIRST.search(text):
            warn(f"turn {i} (female speaker) has a male verb ending: {MALE_FIRST.search(text).group(0)}")
        if gender == "M" and FEMALE_FIRST.search(text):
            warn(f"turn {i} (male speaker) has a female verb ending: {FEMALE_FIRST.search(text).group(0)}")
        for lab in t.get("L", []):
            if lab[1] != "*" and lab[1] not in text:
                err(f"turn {i}: label phrase not in t: {lab[1]!r}")
            if t["s"] != "A":
                err(f"turn {i}: label on a non-agent turn")

    agent_idx = [i for i, t in enumerate(turns) if t["s"] == "A"]
    for i, rules in labelled(sc):
        if "R1" in rules and (len(agent_idx) < 1 or i != agent_idx[0]):
            err("R1 label is not on the first agent turn")
        if "R2" in rules and (len(agent_idx) < 2 or i != agent_idx[1]):
            err("R2 label is not on the second agent turn")

    if old is None:
        warn("no baseline scenario to compare with")
        return
    for key in UNCHANGED:
        if sc.get(key) != old.get(key):
            err(f"field {key} changed: {old.get(key)!r} -> {sc.get(key)!r}")
    if [r for _, r in labelled(sc)] != [r for _, r in labelled(old)]:
        err(f"labelled turns/rule ids changed: {[r for _, r in labelled(old)]} -> {[r for _, r in labelled(sc)]}")
    old_agent_idx = [i for i, t in enumerate(old["turns"]) if t["s"] == "A"]
    if old.get("hero") is not True:
        new_pos = [agent_idx.index(i) for i, _ in labelled(sc)]
        old_pos = [old_agent_idx.index(i) for i, _ in labelled(old)]
        if any(a in (0, 1) or b in (0, 1) for a, b in zip(new_pos, old_pos)) and new_pos != old_pos:
            err(f"R1/R2 turn position changed: agent turns {old_pos} -> {new_pos}")
    if old["turns"] and {t["s"] for t in old["turns"]} != {t["s"] for t in turns}:
        err("set of speakers changed")
    if sc.get("hero") and sc != old:
        err("the hero call must stay untouched")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--base", default="main")
    ap.add_argument("--cost", action="store_true")
    args = ap.parse_args()
    files = [Path(f) for f in args.files] or sorted((CONTENT / "scenarios").glob("*.yaml"))
    errs: list[str] = []
    warns: list[str] = []
    total_td = n = 0
    for f in files:
        rel = f.resolve().relative_to(ROOT).as_posix()
        try:
            new = load(f.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            errs.append(f"{rel}: YAML does not load: {e}")
            continue
        raw = f.read_text(encoding="utf-8")
        if re.search(r"mr-IN|mr_IN", raw):
            errs.append(f"{rel}: mentions mr-IN")
        try:
            old = baseline(args.base, rel)
        except subprocess.CalledProcessError:
            old = {}
        for cid, sc in new.items():
            check_scenario(sc, old.get(cid), errs, warns)
            if not sc.get("hero"):
                total_td += sum(len(t.get("td", "")) for t in sc["turns"])
                n += 1
        for cid in old.keys() - new.keys():
            errs.append(f"{rel}: scenario {cid} is missing")
    for w in warns:
        print("WARN ", w)
    for e in errs:
        print("ERROR", e)
    print(f"\n{n} calls checked, {len(errs)} errors, {len(warns)} warnings")
    if args.cost:
        print(f"td characters (non-hero calls): {total_td}  ->  about Rs {total_td / 1000 * RS_PER_1000_CHARS:.0f} "
              f"(Rs {RS_PER_1000_CHARS}/1000 chars, docs/11)")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
