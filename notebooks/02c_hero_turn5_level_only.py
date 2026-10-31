# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
# ---

# %% [markdown]
# # 02c Hero call turn 5, alternative D: level only (gate G2)
# Plain Prakash take (no tag), the original turn-5 Devanagari text, speed 1.0, same phone chain and same -22 LUFS
# normalisation as his other turns, then a straight +3.5 dB gain (target -18.5 LUFS). No pitch, formant, EQ or compression change.
# Writes `5_D`, `call_D.mp3`, `manifest_D.json` and a trio scene; the current files and A/B/C are not touched.
# Run: `tools/.venv/Scripts/python notebooks/02c_hero_turn5_level_only.py` (add `MARYADA_RUN=1` to spend credits and write files).

# %% Parameters
import json
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
GAIN_DB, TOL_LU, TP_CEIL = 3.5, 0.5, -1.5
DATA = al.ROOT / "data" / "audio"
AUD = DATA / "_audition"
voices_cfg = al.load_yaml("content/voices.yaml")
c06 = next(s for s in al.load_yaml("content/scenarios/02_r3_abuse_threats.yaml")["scenarios"] if s["id"] == "c06")
manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))["c06"]
AGENT = al.target_lufs(voices_cfg, "agent")
TARGET = AGENT + GAIN_DB
P = voices_cfg["params"]["agent"]
VOICE = voices_cfg["hero"]["agent"]["voice"]
TEXT = c06["turns"][4]["td"].strip()
cfg = voices_cfg["phone_chain"]
phone_turns = {i: sf.read(DATA / "c06" / f"{i}.wav", dtype="float32")[0] for i in range(1, 10)}

# %% 1. Cost estimate (printed before anything is generated)
req = al.uncached_requests(TEXT, VOICE, P["language"], P["speed"], 48000)
cost = round(sum(req) * al.RUPEES_PER_CHAR, 2)
print(f"new TTS requests: {len(req)} ({sum(req)} characters), estimated cost Rs {cost}")
assert cost <= MAX_SPEND_INR, f"estimate Rs {cost} is above Rs {MAX_SPEND_INR}: stop and report"
if not RUN:
    raise SystemExit("estimate only (no MARYADA_RUN=1)")


# %% 2. Measuring helpers (same trackers as notebook 02b)
def frames_of(x: np.ndarray, sr: int, win: float = 0.04, hop: float = 0.01) -> np.ndarray:
    n, h = int(sr * win), int(sr * hop)
    return x[np.arange(0, len(x) - n, h)[:, None] + np.arange(n)[None, :]]


def active(fr: np.ndarray) -> np.ndarray:
    rms = np.sqrt(np.mean(fr**2, axis=1) + 1e-12)
    return 20 * np.log10(rms / rms.max()) > -35


def median_f0(x: np.ndarray, sr: int) -> float:
    fr = frames_of(x, sr)
    fr = fr[active(fr)] * np.hanning(fr.shape[1])
    ac = np.fft.irfft(np.abs(np.fft.rfft(fr, 2 * fr.shape[1], axis=1)) ** 2, axis=1)[:, : fr.shape[1]]
    ac /= ac[:, :1] + 1e-12
    lo, hi = int(sr / 400), int(sr / 70)
    lag = lo + np.argmax(ac[:, lo:hi], axis=1)
    voiced = ac[np.arange(len(ac)), lag] > 0.5
    return float(np.median(sr / lag[voiced])) if voiced.any() else float("nan")


def spectral_centre(x: np.ndarray, sr: int) -> float:
    fr = frames_of(x, sr)
    fr = fr[active(fr)] * np.hanning(fr.shape[1])
    power = np.abs(np.fft.rfft(fr, axis=1)) ** 2
    f = np.fft.rfftfreq(fr.shape[1], 1 / sr)
    return float((power.sum(axis=0) * f).sum() / power.sum())


# %% 3. Take, phone chain, -22 LUFS like the other agent turns, then a straight gain with a true-peak guard
client = httpx.Client(timeout=90)
x, sr = al.synthesize(TEXT, VOICE, P["language"], P["speed"], 48000, client)
raw = al.loudnorm(al.trim_silence(x, sr), sr, AGENT)  # as in notebook 02
base = al.phone_voice(raw, sr, AGENT, cfg)
m0 = al.measure_loudness(base, 8000)
room = TP_CEIL - m0["true_peak"]  # dB of gain available before the true peak reaches the ceiling
gain = min(GAIN_DB, room)
t5 = (base * 10 ** (gain / 20)).astype(np.float32)
print(f"new TTS requests sent: {al.requests_made}; base {m0['lufs']:.1f} LUFS, {m0['true_peak']:.1f} dBTP; "
      f"gain applied {gain:+.2f} dB of {GAIN_DB:+.1f} requested (room {room:+.2f} dB)")
if gain < GAIN_DB - 0.5:
    print(f"REPORT: the true-peak limit reduces the gain by {GAIN_DB - gain:.2f} dB (more than 0.5 dB)")

# %% 4. Measured figures against Prakash's normal turns
print(f"\n{'turn':10s} {'f0 Hz':>7s} {'centre Hz':>10s} {'LUFS':>6s} {'dBTP':>6s} {'dur s':>6s}")
rows = {}
for i in (1, 3, 7, 9):
    a = phone_turns[i]
    rows[f"{i} (cur)"] = (a, median_f0(a, 8000), spectral_centre(a, 8000))
rows["5 (cur)"] = (phone_turns[5], median_f0(phone_turns[5], 8000), spectral_centre(phone_turns[5], 8000))
rows["5 (D)"] = (t5, median_f0(t5, 8000), spectral_centre(t5, 8000))
for tag, (a, f0, ce) in rows.items():
    m = al.measure_loudness(a, 8000)
    print(f"{tag:10s} {f0:7.1f} {ce:10.0f} {m['lufs']:6.1f} {m['true_peak']:6.1f} {len(a) / 8000:6.1f}")
normal = [rows[f"{i} (cur)"] for i in (1, 3, 7, 9)]
n_f0, n_ce = float(np.mean([r[1] for r in normal])), float(np.mean([r[2] for r in normal]))
md_ = al.measure_loudness(t5, 8000)
ok = abs(md_["lufs"] - TARGET) <= TOL_LU and md_["true_peak"] <= TP_CEIL
print(f"normal turns (1,3,7,9): f0 {n_f0:.1f} Hz, centre {n_ce:.0f} Hz; D: f0 {12 * np.log2(rows['5 (D)'][1] / n_f0):+.1f} st, "
      f"centre {rows['5 (D)'][2] / n_ce * 100 - 100:+.0f} %; D loudness {md_['lufs']:.1f} LUFS (target {TARGET:g}, "
      f"{'ok' if ok else 'CHECK'}), {md_['true_peak']:.1f} dBTP")

# %% 5. Files: 5_D, call_D.mp3, manifest_D.json, trio scene
al.write_wav(DATA / "c06" / "5_D.wav", t5, 8000)
al.write_mp3(DATA / "c06" / "5_D.mp3", t5, 8000, 64)
seq = [t5 if i == 5 else phone_turns[i] for i in range(1, 10)]
call, offsets = al.assemble_call(seq, 8000, "c06", gap_ms=tuple(cfg["turn_gap_ms"]))
al.write_mp3(DATA / "c06" / "call_D.mp3", call, 8000, 64)
mf = json.loads(json.dumps(manifest))
for t, off, a in zip(mf["turns"], offsets, seq, strict=True):
    t["offset_ms"], t["duration_ms"] = off, round(len(a) * 1000 / 8000)
    if t["idx"] == 5:
        t["wav8k"], t["mp3"] = "c06/5_D.wav", "c06/5_D.mp3"
mf["call_mp3"], mf["duration_ms"] = "c06/call_D.mp3", round(len(call) * 1000 / 8000)
(DATA / "c06" / "manifest_D.json").write_text(json.dumps({"c06": mf}, indent=1), encoding="utf-8")

coach_x, c_sr = sf.read(AUD / "A4_coach_R5__Shubham__V2__raw.wav", dtype="float32")
chime = al.chime_at(al.target_lufs(voices_cfg, "coach"), c_sr)
gap = np.zeros(int(c_sr * 0.4), dtype=np.float32)


def up(a: np.ndarray) -> np.ndarray:
    return signal.resample_poly(a, c_sr, 8000).astype(np.float32)


scene = "trio_c06_turn5_D__Prakash__Shivani_plain__Shubham_plain.wav"
al.write_wav(AUD / scene, np.concatenate([up(phone_turns[4]), gap, up(t5), gap, chime, coach_x, gap, up(phone_turns[6]), gap,
                                          up(phone_turns[7]), gap, up(phone_turns[8])]), c_sr)

# %% 6. INDEX: add D to the block "Hero call turn 5 alternatives"
what = "no tag, original text, speed 1.0, no pitch/EQ/compression change; only the level: +3.5 dB over the agent level (-18.5 LUFS)"
md_path, html_path = AUD / "INDEX.md", AUD / "INDEX.html"
md_add = f"- `../c06/5_D.mp3`, `../c06/call_D.mp3`, `{scene}`: D, {what}"
html_add = (f"<!--hero5altD--><h3>D</h3><p>{what}</p><p>turn 5 only<br><audio controls preload=none src='../c06/5_D.mp3'></audio></p>"
            f"<p>full call<br><audio controls preload=none src='../c06/call_D.mp3'></audio></p>"
            f"<p>scene (turns 4, 5, coach, 6, 7, 8)<br>{scene}<br><audio controls preload=none src='{scene}'></audio></p>")
md_lines = [ln for ln in md_path.read_text(encoding="utf-8").split("\n") if "call_D.mp3" not in ln]
md_path.write_text("\n".join(md_lines).rstrip("\n") + "\n" + md_add, encoding="utf-8")
html_path.write_text(html_path.read_text(encoding="utf-8").split("<!--hero5altD-->")[0] + html_add, encoding="utf-8")
print("INDEX updated:", html_path)
