# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
# ---

# %% [markdown]
# # 01e Audition, shouted threat line with Prakash as the agent (gate G1)
# Same as `01d_audition_shout.py` for the agent voice Prakash: documented `shouting` tag at the very start of turn 5,
# the +3.5 dB variant (target -18.5 LUFS), and two hero scenes. Run after `01d_audition_shout.py`.
# Run: `tools/.venv/Scripts/python notebooks/01e_audition_shout_prakash.py` (add `MARYADA_RUN=1` to spend credits).

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
MAX_SPEND_INR = 10
OUT = al.ROOT / "data" / "audio" / "_audition"
voices_cfg = al.load_yaml("content/voices.yaml")
c06 = next(s for s in al.load_yaml("content/scenarios/02_r3_abuse_threats.yaml")["scenarios"] if s["id"] == "c06")
AGENT = al.target_lufs(voices_cfg, "agent")
GAIN = 3.5  # dB above the plain agent level; the shout is exempt from the +-0.5 LU rule around -22 (see DECISIONS.md)
VOICE, VAR = "Prakash", "V2T_plus3p5"
p = voices_cfg["params"]["agent"]


def job(clip: str, var: str, text: str) -> dict:
    return {"clip": clip, "voice": VOICE, "var": var, "text": text, "group": "agent", "lang": p["language"], "speed": p["speed"]}


T5 = job("A3_agent_threat", "V2S", f"<shouting> {c06['turns'][4]['td'].strip()}")  # documented tag, whole line
T7 = job("H7_agent_T7", "V2", c06["turns"][6]["td"])

# %% 1. Cost estimate (printed before anything is generated)
req = [n for j in (T5, T7) for n in al.uncached_requests(j["text"], VOICE, j["lang"], j["speed"], 48000)]
cost = round(sum(req) * al.RUPEES_PER_CHAR, 2)
print(f"new TTS requests: {len(req)} ({sum(req)} characters), estimated cost Rs {cost}")
assert cost <= MAX_SPEND_INR, f"estimate Rs {cost} is above Rs {MAX_SPEND_INR}: stop and report"

# %% 2. Generate or load, check the first second against the rest
client = httpx.Client(timeout=90)
files, scene_files, rows = [], [], []
if RUN:
    new = al.render_clip(T5, OUT, voices_cfg, client)
    t7 = al.render_clip(T7, OUT, voices_cfg, client)
    print("new TTS requests sent:", al.requests_made)
    x, sr = new["x"], new["sr"]
    first, rest = al.measure_loudness(x[:sr], sr)["lufs"], al.measure_loudness(x[sr:], sr)["lufs"]
    print(f"RAW new take: first 1 s {first:.1f} LUFS, rest {rest:.1f} LUFS, difference {first - rest:+.1f} LU")
    if first < rest - 2.0:
        raise SystemExit("first second is more than 2 LU below the rest: stop and report")

# %% 3. +3.5 dB variant (gain after the phone chain, with the true-peak limiter)
    target = AGENT + GAIN
    stem = f"A3_agent_threat__{VOICE}__{VAR}"
    raw_f, phone_f = OUT / f"{stem}__raw.wav", OUT / f"{stem}__phone.wav"
    if not phone_f.exists():
        al.write_wav(raw_f, al.loudnorm(x, sr, target), sr)
        al.write_wav(phone_f, al.phone_voice(x, sr, target, voices_cfg["phone_chain"]), 8000)
    shout = sf.read(phone_f, dtype="float32")[0]
    files += [(f.name, target, "shouted line +3.5 dB above the plain agent level") for f in (raw_f, phone_f)]
    files += [(f, AGENT, "plain agent level") for f, _ in new["files"] + t7["files"]]

# %% 4. Scenes: Prakash shouting x Shivani (plain, and with her tags) x Shubham plain
    def upsample(a: np.ndarray, rate: int) -> np.ndarray:
        return signal.resample_poly(a, rate, 8000).astype(np.float32)

    def load(clip: str, voice: str, var: str) -> np.ndarray:
        return sf.read(OUT / f"{clip}__{voice}__{var}__phone.wav", dtype="float32")[0]

    coach_x, c_sr = sf.read(OUT / "A4_coach_R5__Shubham__V2__raw.wav", dtype="float32")
    chime = al.chime_at(al.target_lufs(voices_cfg, "coach"), c_sr)
    gap = np.zeros(int(c_sr * 0.4), dtype=np.float32)
    SCENES = {"trio2f__Prakash_V2T_plus3p5__Shivani_V2__Shubham_V2.wav": "V2",
              "trio2g__Prakash_V2T_plus3p5__Shivani_V2T__Shubham_V2.wav": "V2T"}
    for name, b_var in SCENES.items():
        def b(clip: str, var: str = b_var) -> np.ndarray:
            return upsample(load(clip, "Shivani", var), c_sr)

        parts = [("T4 borrower", b("A2_borrower_job"), -24.0), ("T5 agent", upsample(shout, c_sr), AGENT + GAIN),
                 ("chime", chime, -27.0), ("coach", coach_x, -27.0), ("T6 borrower", b("H6_borrower_T6"), -24.0),
                 ("T7 agent", upsample(t7["phone"], c_sr), AGENT), ("T8 borrower", b("H8_borrower_T8"), -24.0)]
        seq = [parts[0][1], gap, parts[1][1], gap, chime, coach_x, gap, parts[4][1], gap, parts[5][1], gap, parts[6][1]]
        al.write_wav(OUT / name, np.concatenate(seq), c_sr)
        scene_files.append(name)
        for seg, a, tgt in parts:
            rows.append((f"{name} / {seg}", tgt, al.measure_loudness(np.tile(a, 8) if seg == "chime" else a, c_sr), "shouted: own target" if "T5" in seg else "same target as before"))

# %% 5. Loudness table ("Round 2 shout Prakash" in LOUDNESS.md) and INDEX
    for fn, tgt, note in files:
        a, rate = sf.read(OUT / fn, dtype="float32")
        rows.append((fn, tgt, al.measure_loudness(a, rate), note))
    lines = ["", "## Round 2 shout Prakash", "",
             "| file | target LUFS | measured LUFS | LRA | true peak dBTP | check | note |", "|---|---|---|---|---|---|---|"]
    bad = 0
    for name, tgt, m, note in rows:
        ok = abs(m["lufs"] - tgt) <= 0.5 and m["true_peak"] <= -1.5
        bad += not ok
        lines.append(f"| {name} | {tgt:g} | {m['lufs']:.1f} | {m['lra']:.1f} | {m['true_peak']:.1f} | {'ok' if ok else 'CHECK'} | {note} |")
        if "T5" in name or name.endswith(f"{VAR}__phone.wav"):
            print(f"{name}: target {tgt:g}, measured {m['lufs']:.1f} LUFS, true peak {m['true_peak']:.1f} dBTP")
    path = OUT / "LOUDNESS.md"
    path.write_text(path.read_text(encoding="utf-8").split("\n## Round 2 shout Prakash")[0] + "\n".join(lines), encoding="utf-8")
    print("files outside their own +-0.5 LU target or above -1.5 dBTP:", bad)

    notes = {"trio2f": "Prakash (agent) with the +3.5 dB shout x Shivani plain x Shubham plain.",
             "trio2g": "Prakash (agent) with the +3.5 dB shout x Shivani with her T4/T6/T8 tags x Shubham plain."}
    md = ["", "## Round 2 shout Prakash", "Prakash as agent: shouting tag at the very start of turn 5, +3.5 dB above the plain agent level.", ""]
    html = ["<!--round2prakash--><h2>Shouted threat line, Prakash as agent</h2><p>Shouting tag at the very start of turn 5, +3.5 dB above the plain agent level.</p>"]
    for var, label in (("V2S", "new take, plain level"), (VAR, "+3.5 dB")):
        for kind in ("phone", "raw"):
            fn = f"A3_agent_threat__{VOICE}__{var}__{kind}.wav"
            md.append(f"- `{fn}`: {label} / {kind}")
            html.append(f"<p>{label} / {kind}<br><audio controls preload=none src='{fn}'></audio></p>")
    for name in scene_files:
        txt = notes[name.split("__")[0]]
        md.append(f"- `{name}`: {txt}")
        html.append(f"<p>{txt}<br>{name}<br><audio controls preload=none src='{name}'></audio></p>")
    md_path, html_path = OUT / "INDEX.md", OUT / "INDEX.html"
    md_path.write_text(md_path.read_text(encoding="utf-8").split("\n## Round 2 shout Prakash")[0] + "\n".join(md), encoding="utf-8")
    html_path.write_text(html_path.read_text(encoding="utf-8").split("<!--round2prakash-->")[0] + "\n".join(html), encoding="utf-8")
    print("INDEX updated:", html_path)
