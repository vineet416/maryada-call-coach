# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
# ---

# %% [markdown]
# # 01b Audition, round 2 (gate G1)
# New samples to compare, all from Devanagari (`V2`) text: Shivani next to Chetana as the hero borrower (three emotions),
# Yashraj, Prakash as neighbour, two hero trio scenes and voice-over alternatives.
# Existing clips and cache entries are reused; only missing ones are requested. Run after `01_audition.py`
# (re-running 01 rebuilds INDEX and the loudness table without this section).
# Run: `tools/.venv/Scripts/python notebooks/01b_audition_round2.py` (add `MARYADA_RUN=1` to spend credits).

# %% Parameters
import os
import sys
from pathlib import Path

import httpx2 as httpx
import numpy as np
import soundfile as sf
from scipy import signal

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import audio_lib as al

RUN = os.environ.get("MARYADA_RUN") == "1"
MAX_SPEND_INR = 20
SR = 48000  # the API honours it (docs/SPIKE-RESULTS.md)
OUT = al.ROOT / "data" / "audio" / "_audition"
voices_cfg = al.load_yaml("content/voices.yaml")
audition = al.load_yaml("content/audition.yaml")
r2 = audition["round2"]
clips = {c["id"]: c for c in audition["clips"]}
c06 = next(s for s in al.load_yaml("content/scenarios/02_r3_abuse_threats.yaml")["scenarios"] if s["id"] == "c06")
td = {n: c06["turns"][n - 1]["td"] for n in (4, 6, 8)}  # borrower turns in Devanagari
assert td[4] == clips["A2_borrower_job"]["variants"]["V2"], "A2 must carry the c06 turn 4 text"
PARAM_KEY = {"agent": "agent", "borrower": "borrower", "third_party": "third", "coach": "coach", "vo": "vo"}


def target_lufs(group: str) -> float:
    return float(str(voices_cfg["loudness"][group]).split()[0])


def job(clip: str, voice: str, var: str, text: str, group: str, lang: str | None = None, speed: float | None = None) -> dict:
    p = voices_cfg["params"][PARAM_KEY[group]]
    return {"clip": clip, "voice": voice, "var": var, "text": text, "group": group,
            "lang": lang or p["language"], "speed": speed or p["speed"]}


# %% 1. Jobs and the cost estimate (printed before anything is generated)
vo_text = r2["vo_devanagari"]
JOBS = [
    job("A2_borrower_job", "Shivani", "V2", td[4], "borrower"),
    job("H6_borrower_T6", "Shivani", "V2", td[6], "borrower"),
    job("H8_borrower_T8", "Shivani", "V2", td[8], "borrower"),
    job("A7_neighbour", "Prakash", "V2", clips["A7_neighbour"]["variants"]["V2"], "third_party"),
    # reused when already generated (cache): the comparison partners and the trio agent and coach
    job("A2_borrower_job", "Chetana", "V2", td[4], "borrower"),
    job("A6_male_borrower", "Yashraj", "V2", clips["A6_male_borrower"]["variants"]["V2"], "borrower"),
    job("A3_agent_threat", "Avinash", "V2", clips["A3_agent_threat"]["variants"]["V2"], "agent"),
    job("A4_coach_R5", "Shubham", "V2", clips["A4_coach_R5"]["variants"]["V2"], "coach"),
    *[job("A8_voiceover", v, "V2", vo_text, "vo", lang="hi-IN", speed=1.0) for v in r2["vo_voices"]],
    job("A8_voiceover", r2["vo_voices"][0], "V2slow", vo_text, "vo", lang="hi-IN", speed=r2["vo_slow_speed"]),
]
need = [(j, al.uncached_requests(j["text"], j["voice"], j["lang"], j["speed"], SR)) for j in JOBS]
new_requests = sum(len(n) for _, n in need)
new_chars = sum(sum(n) for _, n in need)
cost = round(new_chars * al.RUPEES_PER_CHAR, 2)
print(f"{len(JOBS)} clips in this round; plain V2 TTS requests needed: {new_requests} ({new_chars} characters, "
      f"estimated Rs {cost}); V2T (tagged) requests: 0 (waiting for the tag choice)")
for j, n in need:
    print(f"  {j['clip']:18s} {j['voice']:9s} {j['var']:6s} {'cached' if not n else f'{len(n)} request(s)'}")
assert cost <= MAX_SPEND_INR, f"estimate Rs {cost} is above Rs {MAX_SPEND_INR}: stop and report"

# %% 2. Generate or load: raw (clean, loudness-normalised) and phone versions
client = httpx.Client(timeout=90)
audio, files = {}, []


def stem(j: dict) -> str:
    return f"{j['clip']}__{j['voice']}__{j['var']}"


if RUN:
    OUT.mkdir(parents=True, exist_ok=True)
    for j in JOBS:
        target = target_lufs(j["group"])
        raw_f, phone_f = OUT / f"{stem(j)}__raw.wav", OUT / f"{stem(j)}__phone.wav"
        is_call = j["group"] in ("agent", "borrower", "third_party")
        if raw_f.exists() and (phone_f.exists() or not is_call):
            x, sr = sf.read(raw_f, dtype="float32")
            p = sf.read(phone_f, dtype="float32")[0] if is_call else None
            new = False
        else:
            x, sr = al.synthesize(j["text"], j["voice"], j["lang"], j["speed"], SR, client)
            x = al.loudnorm(al.trim_silence(x, sr), sr, target)
            al.write_wav(raw_f, x, sr)
            p = None
            if is_call:
                p = al.phone_voice(x, sr, target, voices_cfg["phone_chain"])
                al.write_wav(phone_f, p, 8000)
            new = True
        audio[(j["clip"], j["voice"], j["var"])] = (x, sr, p)
        files.append({**j, "new": new, "file": raw_f.name, "kind": "raw"})
        if is_call:
            files.append({**j, "new": new, "file": phone_f.name, "kind": "phone"})
    print("new clips written:", sum(f["new"] for f in files), "files | new TTS requests:", al.requests_made)

# %% 3. Trio scenes of the hero call, V2 only: borrower, agent threat, chime, coach
trio_files, trio_segments = [], {}


def upsample(p: np.ndarray, sr: int) -> np.ndarray:
    return signal.resample_poly(p, sr, 8000).astype(np.float32)


if RUN:
    coach_x, c_sr, _ = audio[("A4_coach_R5", "Shubham", "V2")]
    agent_p = audio[("A3_agent_threat", "Avinash", "V2")][2]
    chime = al.chime_at(target_lufs("coach"), c_sr)
    gap = np.zeros(int(c_sr * 0.4), dtype=np.float32)
    for borrower in ("Shivani", "Chetana"):
        b_p = audio[("A2_borrower_job", borrower, "V2")][2]
        parts = [("borrower", upsample(b_p, c_sr), "borrower"), ("agent", upsample(agent_p, c_sr), "agent"),
                 ("chime", chime, "coach"), ("coach", coach_x, "coach")]
        name = f"trio2__Avinash__{borrower}__Shubham__V2.wav"
        al.write_wav(OUT / name, np.concatenate([parts[0][1], gap, parts[1][1], gap, chime, coach_x]), c_sr)
        trio_files.append(name)
        trio_segments[name] = parts
    print("trio scenes:", trio_files)

# %% 4. Loudness check and table (appended to LOUDNESS.md as a Round 2 section)
loud_rows = []
if RUN:
    for f in files:
        x, sr = sf.read(OUT / f["file"], dtype="float32")
        loud_rows.append((f["file"], target_lufs(f["group"]), al.measure_loudness(x, sr)))
    for name, segs in trio_segments.items():
        for seg, x, group in segs:
            probe = np.tile(x, 8) if seg == "chime" else x  # a chime is too short to measure alone
            loud_rows.append((f"{name} / {seg}", target_lufs(group), al.measure_loudness(probe, c_sr)))
    lines = ["", "## Round 2", "", "| file | target LUFS | measured LUFS | LRA | true peak dBTP | check |", "|---|---|---|---|---|---|"]
    bad = 0
    for name, tgt, m in loud_rows:
        ok = abs(m["lufs"] - tgt) <= 0.5 and m["true_peak"] <= -1.5
        bad += not ok
        lines.append(f"| {name} | {tgt:g} | {m['lufs']:.1f} | {m['lra']:.1f} | {m['true_peak']:.1f} | {'ok' if ok else 'CHECK'} |")
    path = OUT / "LOUDNESS.md"
    base = path.read_text(encoding="utf-8").split("\n## Round 2")[0]
    path.write_text(base + "\n".join(lines), encoding="utf-8")
    for tgt in sorted({t for _, t, _ in loud_rows}):
        ms = [m for _, t, m in loud_rows if t == tgt]
        print(f"target {tgt:g} LUFS: {len(ms)} files, measured {min(m['lufs'] for m in ms):.1f} to "
              f"{max(m['lufs'] for m in ms):.1f}, highest true peak {max(m['true_peak'] for m in ms):.1f} dBTP")
    print("round 2 files outside +-0.5 LU or above -1.5 dBTP:", bad)

# %% 5. INDEX (Round 2 section appended; everything earlier is kept)
if RUN:
    def entries(clip: str, voices: list[tuple[str, str]], note: str) -> tuple[list[str], list[str]]:
        md, html = [f"### {clip}", note], [f"<h3>{clip}</h3><p>{note}</p>"]
        for voice, var in voices:
            for f in [f for f in files if f["clip"] == clip and f["voice"] == voice and f["var"] == var]:
                label = f"{voice} / {var} / {f['kind']}" + (" (earlier round)" if not f["new"] else "")
                md.append(f"- `{f['file']}`: {label}")
                html.append(f"<p>{label}<br><audio controls preload=none src='{f['file']}'></audio></p>")
        return md, html

    sections = [
        ("A2_borrower_job", [("Shivani", "V2"), ("Chetana", "V2")], "Hero borrower, turn 4 (worried): Shivani next to Chetana."),
        ("H6_borrower_T6", [("Shivani", "V2")], "Hero borrower, turn 6 (upset, defending herself): Shivani."),
        ("H8_borrower_T8", [("Shivani", "V2")], "Hero borrower, turn 8 (calmer, agreeing): Shivani."),
        ("A6_male_borrower", [("Yashraj", "V2")], "Male borrower: Yashraj."),
        ("A7_neighbour", [("Prakash", "V2")], "Neighbour: Prakash."),
        ("A8_voiceover", [(v, "V2") for v in r2["vo_voices"]] + [(r2["vo_voices"][0], "V2slow")],
         "Voice-over line in Devanagari. V2slow = the first voice at speed 0.9 (the API documents speed 0.85-1.15)."),
    ]
    md = ["", "## Round 2", "All from Devanagari (V2) text. Loudness: LOUDNESS.md, section Round 2.",
          "V2T (tagged) versions are not generated yet: waiting for the tag choice.", ""]
    html = ["<!--round2--><h1>Round 2</h1><p>All from Devanagari (V2) text. <a href='LOUDNESS.md'>Loudness</a>. V2T (tagged) versions: waiting for the tag choice.</p>"]
    for clip, voices, note in sections:
        m, h = entries(clip, voices, note)
        md += m + [""]
        html += h
    md += ["### Hero trio scenes (V2)", "Borrower (turn 4), agent threat (Avinash), chime, coach (Shubham). Compare Shivani with Chetana.", ""]
    html.append("<h3>Hero trio scenes (V2)</h3><p>Borrower, agent threat (Avinash), chime, coach (Shubham). Compare Shivani with Chetana.</p>")
    for name in trio_files:
        md.append(f"- `{name}`")
        html.append(f"<p>{name}<br><audio controls preload=none src='{name}'></audio></p>")
    md_path, html_path = OUT / "INDEX.md", OUT / "INDEX.html"
    md_path.write_text(md_path.read_text(encoding="utf-8").split("\n## Round 2")[0] + "\n".join(md), encoding="utf-8")
    html_path.write_text(html_path.read_text(encoding="utf-8").split("<!--round2-->")[0] + "\n".join(html), encoding="utf-8")
    print("INDEX.md and INDEX.html updated:", html_path)

# %% 6. Notes
# Tags: the Timbre v3.0 docs list 13 audio tags (laugh, giggle, sigh, exhales, sniffles, yawns, coughs, clears throat,
# whispers, shouting, excited, slow, pauses). "angry" is not one of them; unknown tags are stripped silently.
# V2T clips are therefore not generated until the user picks documented tags per clip.
