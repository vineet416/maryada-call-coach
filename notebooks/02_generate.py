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
import sys
from pathlib import Path

import httpx2 as httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import audio_lib as al

SCOPE = "hero"  # "hero" | "all"
ONLY: list[str] = []  # optional scenario ids
RUN = os.environ.get("MARYADA_RUN") == "1"
STT = os.environ.get("MARYADA_STT") == "1"
MAX_SPEND_INR = 15
DATA = al.ROOT / "data" / "audio"
voices_cfg = al.load_yaml("content/voices.yaml")
phrases = al.load_yaml("content/rules_phrases.yaml")
audition = al.load_yaml("content/audition.yaml")
ROLE = {"A": "agent", "B": "borrower", "T": "third_party"}
PARAM_KEY = {"agent": "agent", "borrower": "borrower", "third_party": "third", "coach": "coach", "vo": "vo"}
VOICE = {r: v["voice"] for r, v in voices_cfg["hero"].items()}  # hero call only; the library pool is picked per call later
SHOUT_TURN = {"c06": 5}  # the only tagged line: the agent's threat (voices.yaml tags)
SHOUT_LUFS = al.target_lufs(voices_cfg, "agent") + voices_cfg["tags"]["shout_gain_db"]
scenarios = [s for f in sorted((al.ROOT / "content" / "scenarios").glob("*.yaml")) for s in al.load_yaml(f"content/scenarios/{f.name}")["scenarios"]]
scenarios = [s for s in scenarios if (s["id"] in ONLY if ONLY else s.get("hero") if SCOPE == "hero" else True)]
assert all(s.get("hero") for s in scenarios), "voice selection from library_pool is not built yet: hero scope only"
print("scenarios:", [s["id"] for s in scenarios])


# %% 1. Jobs and the cost estimate (printed before anything is generated)
def turn_job(sc: dict, i: int) -> dict:
    t = sc["turns"][i - 1]
    role = ROLE[t["s"]]
    text = t["td"].strip()
    shout = SHOUT_TURN.get(sc["id"]) == i
    if shout:
        text = f"<shouting> {text}"
    p = voices_cfg["params"][PARAM_KEY[role]]
    target = SHOUT_LUFS if shout else al.target_lufs(voices_cfg, role)
    return {"sc": sc["id"], "idx": i, "s": t["s"], "role": role, "voice": VOICE[role], "text": text, "lang": p["language"],
            "speed": p["speed"], "target": target, "shout": shout, "ref": t["t"]}


jobs = [turn_job(sc, i) for sc in scenarios for i in range(1, len(sc["turns"]) + 1)]
coach_jobs = []
if SCOPE == "hero" or not ONLY:
    p = voices_cfg["params"]["coach"]
    for rule, lines in phrases["coach_lines_td"].items():
        coach_jobs += [{"rule": rule, "n": n, "voice": VOICE["coach"], "text": line, "lang": p["language"], "speed": p["speed"]}
                       for n, line in enumerate(lines, 1)]
chars = sum(sum(al.uncached_requests(j["text"], j["voice"], j["lang"], j["speed"], 48000)) for j in jobs + coach_jobs)
cost = round(chars * al.RUPEES_PER_CHAR, 2)
print(f"turns: {len(jobs)}, coach lines: {len(coach_jobs)}; uncached characters: {chars}, estimated cost Rs {cost}")
assert cost <= MAX_SPEND_INR, f"estimate Rs {cost} is above Rs {MAX_SPEND_INR}: stop and report"
for j in jobs:
    assert j["voice"] == VOICE[j["role"]]
    assert ("<" in j["text"]) == j["shout"], "tags only on the agent threat line"

# %% 2. Turns: raw (clean, normalised), phone chain (8 kHz WAV + MP3)
client = httpx.Client(timeout=90)
turns: dict[str, list[dict]] = {}
if RUN:
    for sc in scenarios:
        arrays = []
        for j in [x for x in jobs if x["sc"] == sc["id"]]:
            x, sr = al.synthesize(j["text"], j["voice"], j["lang"], j["speed"], 48000, client)
            raw = al.loudnorm(al.trim_silence(x, sr), sr, j["target"])
            phone = al.phone_voice(raw, sr, j["target"], voices_cfg["phone_chain"])
            al.write_wav(DATA / "raw" / sc["id"] / f"{j['idx']}.wav", raw, sr)
            al.write_wav(DATA / sc["id"] / f"{j['idx']}.wav", phone, 8000)
            al.write_mp3(DATA / sc["id"] / f"{j['idx']}.mp3", phone, 8000, 64)
            arrays.append(phone)
            turns.setdefault(sc["id"], []).append({**j, "phone": phone, "raw": raw, "sr": sr})
    print("new TTS requests so far:", al.requests_made)

# %% 3. call.mp3 with per-turn offsets, manifest.json
manifest = {}
if RUN:
    for sc in scenarios:
        t = turns[sc["id"]]
        call, offsets = al.assemble_call([x["phone"] for x in t], 8000, sc["id"], gap_ms=tuple(voices_cfg["phone_chain"]["turn_gap_ms"]))
        al.write_mp3(DATA / sc["id"] / "call.mp3", call, 8000, 64)
        manifest[sc["id"]] = {
            "turns": [{"idx": x["idx"], "speaker": x["s"], "wav8k": f"{sc['id']}/{x['idx']}.wav", "mp3": f"{sc['id']}/{x['idx']}.mp3",
                       "duration_ms": round(len(x["phone"]) * 1000 / 8000), "offset_ms": o} for x, o in zip(t, offsets, strict=True)],
            "call_mp3": f"{sc['id']}/call.mp3", "duration_ms": round(len(call) * 1000 / 8000)}
    (DATA / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")

# %% 4. Coach nudges (clean full-band, not phone-processed), earcon, coach_manifest.json
coach_files = []
if RUN:
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
if RUN:
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
    print(f"coach files: {len(coach_files)} (6 rules x 3 + 2 praise = 20 expected), earcon exists: {(DATA / 'coach' / 'earcon.mp3').exists()}")
    print("problems:", problems or "none")

# %% 6. STT round trip on the hero turns (agent >= 80 %, borrower >= 60 % keyword recovery, docs/06)
if RUN and STT:
    al.spike.HINTS[:] = audition["stt_roundtrip"]["key_terms_hint"]
    scores: dict[str, list[float]] = {"agent": [], "borrower": []}
    for x in turns["c06"]:
        text, _, _ = al.stt_realtime(DATA / "c06" / f"{x['idx']}.wav", "hi-IN")
        r = al.recovery(al.key_terms(x["ref"]), text)
        scores[x["role"]].append(r)
        print(f"turn {x['idx']} {x['role']:8s} recovery {r:.2f} | {text[:70]}")
    for role, need in (("agent", 0.8), ("borrower", 0.6)):
        mean = sum(scores[role]) / len(scores[role])
        print(f"{role}: mean recovery {mean:.2f} (needs >= {need}) {'PASS' if mean >= need else 'FAIL'}")
