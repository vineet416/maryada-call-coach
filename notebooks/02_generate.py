# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
# ---

# %% [markdown]
# # 02 Generate call audio (gate G2 for the hero call)
# Turns of the selected scenarios with the final single-voice casting (`content/voices.yaml`), the coach nudges,
# the earcon and the manifests. SCOPE="hero" builds c06 only.
# Run: `tools/.venv/Scripts/python notebooks/02_generate.py` (add `MARYADA_RUN=1` to spend credits, `MARYADA_STT=1`
# for the speech-to-text round trip on the hero turns).

# %% Parameters
import json
import os
import shutil
import sys
import time
from pathlib import Path

import httpx2 as httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import audio_lib as al

SCOPE = "library"  # the 29 library calls; the hero call c06 is final and committed: it is never regenerated here
ONLY: list[str] = []  # optional scenario ids
RUN = os.environ.get("MARYADA_RUN") == "1"
STT = os.environ.get("MARYADA_STT") == "1"
C2 = os.environ.get("MARYADA_C2") == "1"  # checkpoint C2: a small listening set into data/audio/_c2 (not the library folders)
MAX_SPEND_INR = 59  # total cap for the library (C2 lines + the rest); the ledger below carries the spend across runs
DATA = al.ROOT / "data" / "audio"
voices_cfg = al.load_yaml("content/voices.yaml")
phrases = al.load_yaml("content/rules_phrases.yaml")
audition = al.load_yaml("content/audition.yaml")
agents = {a["id"]: a for a in al.load_yaml("content/agents.yaml")["agents"]}
ROLE = {"A": "agent", "B": "borrower", "T": "third_party"}
PARAM_KEY = {"agent": "agent", "borrower": "borrower", "third_party": "third", "coach": "coach", "vo": "vo"}
TOLERANCE_DB = 1.0  # library calls only (decided 2026-11-01, was 0.5); a line below +2.5 dB real gain is listed in the report
RAISE = voices_cfg["violation_gain"]  # agent lines that carry a violation label: level only (+3.5 dB), nothing else
COACH = os.environ.get("MARYADA_COACH") == "1"  # the coach lines and the earcon are final; only rebuilt on request
LEDGER = DATA / "_cache" / "spend.json"
spent_inr = json.loads(LEDGER.read_text())["inr"] if LEDGER.exists() else 0.0
scenarios = [s for f in sorted((al.ROOT / "content" / "scenarios").glob("*.yaml")) for s in al.load_yaml(f"content/scenarios/{f.name}")["scenarios"]]
assert not ONLY or not any(s.get("hero") and s["id"] in ONLY for s in scenarios), "the hero call is never regenerated"
scenarios = [s for s in scenarios if not s.get("hero") and (s["id"] in ONLY if ONLY else True)]
CAST = {s["id"]: al.pick_voices(s, agents, voices_cfg["library_pool"]) for s in scenarios}
for sid, c in CAST.items():
    people = [v for r, v in c.items() if r != "coach"]
    assert len(set(people)) == len(people) and c["coach"] not in people, f"{sid}: voices shared inside the call"
print("scenarios:", len(scenarios), "| spent so far Rs", round(spent_inr, 2))


# %% 1. Jobs and the cost estimate (printed before anything is generated)
def turn_job(sc: dict, i: int) -> dict:
    t = sc["turns"][i - 1]
    role = ROLE[t["s"]]
    text = t["td"].strip()
    raised = role == "agent" and any(rule != "G1" for rule, _ in t.get("L", []))
    p = voices_cfg["params"][PARAM_KEY[role]]
    base = al.target_lufs(voices_cfg, role)
    return {"sc": sc["id"], "idx": i, "s": t["s"], "role": role, "voice": CAST[sc["id"]][role], "text": text, "lang": p["language"],
            "speed": p["speed"], "base": base, "target": base + RAISE["gain_db"] if raised else base, "raised": raised,
            "ref": t["t"], "labels": [ph for _, ph in t.get("L", [])]}


jobs = [turn_job(sc, i) for sc in scenarios for i in range(1, len(sc["turns"]) + 1)]
C2_NOTES = {}  # (scenario, turn) -> what to listen for
if C2:  # one whole short call (c15) plus single lines that cover every voice and the +3.5 dB case
    def first(sid, speaker, min_chars=0):
        return next(j for j in jobs if j["sc"] == sid and j["s"] == speaker and len(j["text"]) >= min_chars)
    singles = [(first("c11", "A", 0), "Avinash agent line"),
               (next(j for j in jobs if j["sc"] == "c11" and j["raised"]), "Avinash agent VIOLATION line, +3.5 dB"),
               (next(j for j in jobs if j["sc"] == "c07" and j["raised"]), "Chetana agent VIOLATION line, +3.5 dB"),
               (first("c01", "A", 60), "Chetana agent line, normal level"),
               (first("c03", "B", 25), "Shivani as borrower"),
               (first("c16", "T"), "Avinash as third party (neighbour)"),
               (first("c18", "T"), "Chetana as third party (spouse)")]
    c15 = [j for j in jobs if j["sc"] == "c15"]
    jobs = c15 + [j for j, _ in singles]
    C2_NOTES = {(j["sc"], j["idx"]): n for j, n in singles}
coach_jobs = []
if COACH:
    p = voices_cfg["params"]["coach"]
    for rule, lines in phrases["coach_lines_td"].items():
        coach_jobs += [{"rule": rule, "n": n, "voice": voices_cfg["hero"]["coach"]["voice"], "text": line, "lang": p["language"], "speed": p["speed"]}
                       for n, line in enumerate(lines, 1)]
chars = sum(sum(al.uncached_requests(j["text"], j["voice"], j["lang"], j["speed"], 48000)) for j in jobs + coach_jobs)
cost = round(chars * al.RUPEES_PER_CHAR, 2)
print(f"turns: {len(jobs)}, coach lines: {len(coach_jobs)}; uncached characters: {chars}, estimated cost Rs {cost}")
assert spent_inr + cost <= MAX_SPEND_INR, f"Rs {spent_inr:.2f} spent + Rs {cost} estimated is above Rs {MAX_SPEND_INR}: stop and report"
for j in jobs:
    assert j["voice"] == CAST[j["sc"]][j["role"]]
    assert "<" not in j["text"], "no audio tags anywhere"

# %% 2. Turns: raw (clean, normalised), phone chain (8 kHz WAV + MP3)
client = httpx.Client(timeout=90)


def render_turn(j: dict) -> tuple[np.ndarray, np.ndarray, int]:
    """TTS (cache first), trim, normalise, phone chain; a violation line gets +3.5 dB over the agent level (nothing else)."""
    x, sr = al.synthesize(j["text"], j["voice"], j["lang"], j["speed"], 48000, client)
    raw = al.loudnorm(al.trim_silence(x, sr), sr, j["base"])
    phone = al.phone_voice(raw, sr, j["base"], voices_cfg["phone_chain"])
    if j["raised"]:  # level only (+3.5 dB), the true-peak ceiling may only cost TOLERANCE_DB
        before = al.measure_loudness(phone, 8000)["lufs"]
        room = RAISE["true_peak_dbtp"] - al.measure_loudness(phone, 8000)["true_peak"]
        gain = min(RAISE["gain_db"], room)
        j["limiter_db"] = 0.0
        if gain < RAISE["gain_db"] - TOLERANCE_DB and not j.get("hero"):
            # approved for library lines below the floor: full +3.5 dB, then a true-peak limiter at -1.5 dBTP (see DECISIONS.md)
            phone, j["limiter_db"] = al.limit_true_peak(phone * 10 ** (RAISE["gain_db"] / 20), RAISE["true_peak_dbtp"])
            j["limited"] = True
        else:
            phone = (phone * 10 ** (gain / 20)).astype(np.float32)
        j["gain"] = round(al.measure_loudness(phone, 8000)["lufs"] - before, 2)  # real final gain in loudness
        j["target"] = j["base"] + (RAISE["gain_db"] if j.get("limited") else gain)
        print(f"{j['sc']} turn {j['idx']}: final gain {j['gain']:+.2f} dB of {RAISE['gain_db']:+.1f}, limiter reduction {j['limiter_db']:.2f} dB")
    return raw, phone, sr


def book_spend() -> None:
    """The estimate was computed from the uncached requests, so it is what this run charged; add it to the ledger."""
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps({"inr": round(spent_inr + cost, 2)}))
    print(f"credits used by this run: Rs {cost} (cumulative Rs {spent_inr + cost:.2f} of Rs {MAX_SPEND_INR}); TTS requests sent: {al.requests_made}")


turns: dict[str, list[dict]] = {}
if RUN and not C2:
    for sc in scenarios:
        arrays = []
        for d in (DATA / sc["id"], DATA / "raw" / sc["id"]):  # keep the previous version as a local backup, leave no stale file behind
            if d.exists():
                shutil.move(str(d), str(DATA / "_backup" / f"{d.parent.name}_{d.name}_{time.strftime('%Y%m%d%H%M%S')}"))
        for j in [x for x in jobs if x["sc"] == sc["id"]]:
            raw, phone, sr = render_turn(j)
            al.write_wav(DATA / "raw" / sc["id"] / f"{j['idx']}.wav", raw, sr)
            al.write_wav(DATA / sc["id"] / f"{j['idx']}.wav", phone, 8000)
            al.write_mp3(DATA / sc["id"] / f"{j['idx']}.mp3", phone, 8000, 64)
            arrays.append(phone)
            turns.setdefault(sc["id"], []).append({**j, "phone": phone, "raw": raw, "sr": sr})
    lim = [(x["sc"], x["idx"], x["voice"], x["gain"], round(x["limiter_db"], 2)) for t in turns.values() for x in t if x.get("limited")]
    print(f"violation lines limited to reach +3.5 dB: {len(lim)} of {sum(x['raised'] for t in turns.values() for x in t)}: {lim}")
    book_spend()

# %% 2b. Checkpoint C2: the listening set, written to data/audio/_c2 (git-ignored) with an INDEX
if RUN and C2:
    out = DATA / "_c2"
    out.mkdir(parents=True, exist_ok=True)
    rows, phones = [], []
    for j in jobs:
        raw, phone, sr = render_turn(j)
        m = al.measure_loudness(phone, 8000)
        name = f"{j['sc']}_t{j['idx']}_{j['role']}_{j['voice']}" + ("_VIOLATION" if j["raised"] else "")
        al.write_mp3(out / f"{name}.mp3", phone, 8000, 64)
        note = C2_NOTES.get((j["sc"], j["idx"]), "part of the whole call")
        rows.append(f"| `{name}.mp3` | {note} | {m['lufs']:.1f} (target {j['target']:.1f}) | {f"{j['gain']:+.2f} dB" if j['raised'] else '-'} | {len(phone) / 8000:.1f} s | {j['ref']} |")
        if j["sc"] == "c15":
            phones.append(phone)
    call, _ = al.assemble_call(phones, 8000, "c15", gap_ms=tuple(voices_cfg["phone_chain"]["turn_gap_ms"]))
    al.write_mp3(out / "WHOLE_CALL_c15.mp3", call, 8000, 64)
    intro = ["# C2 listening set (synthetic, phone chain, as the browser will play it)", "",
             "Listen first to `WHOLE_CALL_c15.mp3` (Prakash agent, Yashraj borrower, Shivani third party; turn 5 is a violation line at +3.5 dB),",
             "then the single lines.",
             "Listen for: Hinglish sounds Mumbai-natural; numbers and words like EMI, Tarang Finserv, pending; the violation line is louder",
             "but not distorted; every voice distinct from the others in its call; levels balanced together.", "",
             "| file | what it is | loudness LUFS | applied gain | length | line |", "|---|---|---|---|---|---|"]
    outro = ["", "Reply with one message: OK, or per file: change voice / change line / pronunciation problem."]
    (out / "INDEX.md").write_text(chr(10).join(intro + rows + outro) + chr(10), encoding="utf-8")
    book_spend()
    print(f"C2 files in {out}")

# %% 3. call.mp3 with per-turn offsets, manifest.json
manifest = {}
if RUN and not C2:
    for sc in scenarios:
        t = turns[sc["id"]]
        call, offsets = al.assemble_call([x["phone"] for x in t], 8000, sc["id"], gap_ms=tuple(voices_cfg["phone_chain"]["turn_gap_ms"]))
        al.write_mp3(DATA / sc["id"] / "call.mp3", call, 8000, 64)
        manifest[sc["id"]] = {
            "turns": [{"idx": x["idx"], "speaker": x["s"], "wav8k": f"{sc['id']}/{x['idx']}.wav", "mp3": f"{sc['id']}/{x['idx']}.mp3",
                       "duration_ms": round(len(x["phone"]) * 1000 / 8000), "offset_ms": o,
                       **({"violation_gain_db": x["gain"], "limiter_reduction_db": round(x["limiter_db"], 2)} if x["raised"] else {})} for x, o in zip(t, offsets, strict=True)],
            "call_mp3": f"{sc['id']}/call.mp3", "duration_ms": round(len(call) * 1000 / 8000)}
    old = json.loads((DATA / "manifest.json").read_text(encoding="utf-8")) if (DATA / "manifest.json").exists() else {}
    merged = {**old, **manifest}  # keep entries of calls that are not rebuilt in this run (the hero call c06)
    (DATA / "manifest.json").write_text(json.dumps(dict(sorted(merged.items())), indent=1), encoding="utf-8")

# %% 4. Coach nudges (clean full-band, not phone-processed), earcon, coach_manifest.json
coach_files = []
if RUN and COACH and not C2:
    coach_target = al.target_lufs(voices_cfg, "coach")
    for j in coach_jobs:
        x, sr = al.synthesize(j["text"], j["voice"], j["lang"], j["speed"], 48000, client)
        y = al.loudnorm(al.trim_silence(x, sr), sr, coach_target)
        name = f"{j['rule']}_{j['n']}.mp3"
        al.write_mp3(DATA / "coach" / name, y, sr, 128)
        coach_files.append({"file": name, "rule": j["rule"], "n": j["n"], "duration_ms": round(len(y) * 1000 / sr), "y": y, "sr": sr})
    chime = al.chime_at(coach_target, 24000)
    al.write_mp3(DATA / "coach" / "earcon.mp3", chime, 24000, 128)
    (DATA / "coach_manifest.json").write_text(json.dumps(
        {"earcon": "earcon.mp3", "lines": [{k: v for k, v in c.items() if k not in ("y", "sr")} for c in coach_files]}, indent=1), encoding="utf-8")
    print("new TTS requests in total:", al.requests_made)


# %% 5. Validation: files, durations, clipping, silence, loudness (each file against its own target)
def silence_ratio(x: np.ndarray, sr: int) -> float:
    n = int(sr * 0.02)
    rms = np.sqrt(np.mean(x[: len(x) // n * n].reshape(-1, n) ** 2, axis=1) + 1e-12)
    return float(np.mean(20 * np.log10(rms) < -50))


problems = []
if RUN and not C2:
    print(f"{'file':14s} {'role':11s} {'dur s':>6s} {'peak dBFS':>9s} {'sil %':>5s} {'target':>7s} {'LUFS':>6s} {'dBTP':>6s}")
    for sc in scenarios:
        for x in turns[sc["id"]]:
            for rel in (f"{sc['id']}/{x['idx']}.wav", f"{sc['id']}/{x['idx']}.mp3", f"raw/{sc['id']}/{x['idx']}.wav"):
                if not (DATA / rel).exists():
                    problems.append(f"missing {rel}")
            m = al.measure_loudness(x["phone"], 8000)
            dur, peak, sil = len(x["phone"]) / 8000, al.peak_dbfs(x["phone"]), silence_ratio(x["phone"], 8000)
            print(f"{sc['id']}/{x['idx']:<11d} {x['role']:11s} {dur:6.1f} {peak:9.1f} {sil * 100:5.0f} {x['target']:7.1f} {m['lufs']:6.1f} {m['true_peak']:6.1f}")
            for bad, why in ((not 0.6 <= dur <= 25, "duration"), (peak >= -1.0, "clipping"), (sil >= 0.4, "silence ratio"),
                             (abs(m["lufs"] - x["target"]) > 0.5, "loudness"), (m["true_peak"] > -1.5, "true peak")):
                if bad:
                    problems.append(f"{sc['id']}/{x['idx']}: {why}")
    for c in coach_files:
        m = al.measure_loudness(c["y"], c["sr"])
        ok = abs(m["lufs"] - al.target_lufs(voices_cfg, "coach")) <= 0.5 and m["true_peak"] <= -1.5 and al.peak_dbfs(c["y"]) < -1.0
        if not ok or not (DATA / "coach" / c["file"]).exists() or not 0.6 <= c["duration_ms"] / 1000 <= 25:
            problems.append(f"coach/{c['file']}: check")
    for sc in scenarios:
        expected = {f"{x['idx']}.{e}" for x in turns[sc["id"]] for e in ("wav", "mp3")} | {"call.mp3"}
        stale = sorted(f.name for f in (DATA / sc["id"]).iterdir() if f.name not in expected)
        if stale:
            problems.append(f"stale files in {sc['id']}: {stale}")
    total = sum(m["duration_ms"] for m in manifest.values()) / 1000
    print(f"{len(manifest)} calls, {sum(len(t) for t in turns.values())} turns, {total:.0f} s of call audio")
    print("problems:", problems or "none")

# %% 6. STT round trip on the library turns (agent >= 80 %, borrower >= 60 % keyword recovery, docs/06); costs STT credits, off by default
if RUN and STT and not C2:
    al.spike.HINTS[:] = audition["stt_roundtrip"]["key_terms_hint"]
    scores: dict[str, list[float]] = {"agent": [], "borrower": []}
    for sid, tt in turns.items():
        for x in tt:
            if x["role"] in scores:
                text, _, _ = al.stt_realtime(DATA / sid / f"{x['idx']}.wav", "hi-IN")
                scores[x["role"]].append(al.recovery(al.key_terms(x["ref"]), text))
    for role, need in (("agent", 0.8), ("borrower", 0.6)):
        mean = sum(scores[role]) / max(len(scores[role]), 1)
        print(f"{role}: mean recovery {mean:.2f} (needs >= {need}) {'PASS' if mean >= need else 'FAIL'}")
