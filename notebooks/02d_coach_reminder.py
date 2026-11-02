# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
# ---

# %% [markdown]
# # 02d The Speak live reminder clip (coach/SELECT_1)
# One new coach line, "choose who you are speaking with", spoken by the coach voice. It is built exactly like the other coach
# clips (clean full-band, Devanagari text, loudness-normalised to the coach target, MP3 128 kbps) and added to
# `coach_manifest.json`. No existing clip or manifest entry is touched.
# Run: `tools/.venv/Scripts/python notebooks/02d_coach_reminder.py` prints the cost estimate; add `MARYADA_RUN=1` to generate.

# %% Parameters
import json
import os
import sys
from pathlib import Path

import httpx2 as httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import audio_lib as al

KEY = "SELECT"
RUN = os.environ.get("MARYADA_RUN") == "1"
DATA = al.ROOT / "data" / "audio"
voices_cfg = al.load_yaml("content/voices.yaml")
phrases = al.load_yaml("content/rules_phrases.yaml")
params = voices_cfg["params"]["coach"]
voice = voices_cfg["hero"]["coach"]["voice"]
text = phrases["reminder_lines_td"][KEY][0].strip()
assert "<" not in text, "no audio tags anywhere"

# %% 1. Cost estimate (printed before anything is generated)
chars = sum(al.uncached_requests(text, voice, params["language"], params["speed"], 48000))
print(f"voice {voice}, {len(text)} characters, uncached characters {chars}, estimated cost Rs {round(chars * al.RUPEES_PER_CHAR, 2)}")

# %% 2. Generate, normalise like the other coach clips, write, add to the manifest
if RUN:
    client = httpx.Client(timeout=90)
    target = al.target_lufs(voices_cfg, "coach")
    x, sr = al.synthesize(text, voice, params["language"], params["speed"], 48000, client)
    y = al.loudnorm(al.trim_silence(x, sr), sr, target)
    name = f"{KEY}_1.mp3"
    al.write_mp3(DATA / "coach" / name, y, sr, 128)
    m = al.measure_loudness(y, sr)
    dur = round(len(y) * 1000 / sr)
    ok = abs(m["lufs"] - target) <= 0.5 and m["true_peak"] <= -1.5 and al.peak_dbfs(y) < -1.0 and 0.6 <= dur / 1000 <= 25
    print(f"{name}: {dur} ms, {m['lufs']:.1f} LUFS (target {target}), {m['true_peak']:.1f} dBTP, peak {al.peak_dbfs(y):.1f} dBFS ->", "OK" if ok else "CHECK")
    assert ok, "the clip is outside the coach loudness or duration limits"
    path = DATA / "coach_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["lines"] = [ln for ln in manifest["lines"] if ln["rule"] != KEY] + [{"file": name, "rule": KEY, "n": 1, "duration_ms": dur}]
    path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print("new TTS requests:", al.requests_made, "| file:", DATA / "coach" / name)
