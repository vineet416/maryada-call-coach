# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
# ---

# %% [markdown]
# # 02b Hero call turn 5: alternatives for the raised-voice line (gate G2)
# The shouted turn 5 of c06 sounds like a different, higher voice. This notebook measures pitch (median f0) and spectral
# centre for every agent turn, then builds three alternatives of turn 5 as separate files (`5_A/B/C`, `call_A/B/C.mp3`,
# `manifest_A/B/C.json` in `data/audio/c06/`); the current `call.mp3`, the other turns, coach, earcon and borrower
# are not touched.
#   A: no tag, harder delivery (punctuation, speed 1.1, presence boost, light compression), +2.5 dB.
#   B: the existing tagged take, pitch shifted down to Prakash's normal pitch (formant preserved), +2.5 dB.
#   C: plain opening words + the tagged threat sentences as a separate pitch-corrected clip, short gap, +2.5 dB on the threat.
# Run: `tools/.venv/Scripts/python notebooks/02b_hero_turn5_alternatives.py` (add `MARYADA_RUN=1` to spend credits and write files).

# %% Parameters
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import httpx2 as httpx
import numpy as np
import soundfile as sf
from scipy import signal

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import audio_lib as al

RUN = os.environ.get("MARYADA_RUN") == "1"
MAX_SPEND_INR = 10
DATA = al.ROOT / "data" / "audio"
AUD = DATA / "_audition"
voices_cfg = al.load_yaml("content/voices.yaml")
c06 = next(s for s in al.load_yaml("content/scenarios/02_r3_abuse_threats.yaml")["scenarios"] if s["id"] == "c06")
manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))["c06"]
AGENT = al.target_lufs(voices_cfg, "agent")
SHOUT = voices_cfg["tags"]["shout_target_lufs"]  # -19.5 LUFS integrated
P = voices_cfg["params"]["agent"]
VOICE = voices_cfg["hero"]["agent"]["voice"]
TEXT = c06["turns"][4]["td"].strip()
phone_turns = {i: sf.read(DATA / "c06" / f"{i}.wav", dtype="float32")[0] for i in range(1, 10)}
AGENT_TURNS = [1, 3, 5, 7, 9]  # turn 5 is the shouted one


# %% 1. Measuring: median f0 (autocorrelation) and spectral centre over the speech frames
def frames_of(x: np.ndarray, sr: int, win: float = 0.04, hop: float = 0.01) -> np.ndarray:
    n, h = int(sr * win), int(sr * hop)
    idx = np.arange(0, len(x) - n, h)[:, None] + np.arange(n)[None, :]
    return x[idx]


def active(fr: np.ndarray) -> np.ndarray:
    rms = np.sqrt(np.mean(fr**2, axis=1) + 1e-12)
    return 20 * np.log10(rms / rms.max()) > -35


def median_f0(x: np.ndarray, sr: int) -> float:
    fr = frames_of(x, sr)
    fr = fr[active(fr)] * np.hanning(fr.shape[1])
    spec = np.fft.rfft(fr, 2 * fr.shape[1], axis=1)
    ac = np.fft.irfft(np.abs(spec) ** 2, axis=1)[:, : fr.shape[1]]
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


def stats(x: np.ndarray, sr: int = 8000) -> dict[str, float]:
    return {"f0": median_f0(x, sr), "centre": spectral_centre(x, sr), "dur": len(x) / sr}


def semitones(a: float, b: float) -> float:
    return 12 * np.log2(a / b)


print("Diagnosis: final phone WAVs of the agent turns (8 kHz)")
base = {i: stats(phone_turns[i]) for i in AGENT_TURNS}
for i, s in base.items():
    print(f"  turn {i}{' (shouted)' if i == 5 else '          '}: median f0 {s['f0']:6.1f} Hz | spectral centre {s['centre']:6.0f} Hz | {s['dur']:5.1f} s")
normal = [base[i] for i in AGENT_TURNS if i != 5]
N_F0, N_CENTRE = float(np.mean([s["f0"] for s in normal])), float(np.mean([s["centre"] for s in normal]))
print(f"  normal Prakash turns: f0 {N_F0:.1f} Hz, centre {N_CENTRE:.0f} Hz; shouted turn: f0 {semitones(base[5]['f0'], N_F0):+.1f} semitones, "
      f"centre {base[5]['centre'] / N_CENTRE * 100 - 100:+.0f} %; seconds under the tag: {base[5]['dur']:.1f} (tag at the start covers the whole turn)")
F0_TOL, CENTRE_MAX = 2.0, 1.30  # target: within +-2 semitones, centre at most 30 % above normal

# %% 2. Jobs and the cost estimate (printed before anything is generated)
SENTENCES = re.split(r"(?<=[.!?।])\s+", TEXT)
OPEN, THREAT = SENTENCES[0], " ".join(SENTENCES[1:])
# A: stronger punctuation and shorter sentences in the td text only; every label phrase of turn 5 stays contiguous
TEXT_A = TEXT.replace("नहीं हुआ ना, तो मैं पुलिस को भेजूँगा आपके घर, और", "नहीं हुआ ना, तो मैं पुलिस को भेजूँगा आपके घर! और")
TEXT_A = re.sub(r"।", "!", TEXT_A)
for phrase in ("पुलिस को भेजूँगा आपके घर", "आपके मोहल्ले में सबको बता दूँगा कि आप डिफॉल्टर हो", "कोर्ट का नोटिस भी कल सुबह आ जाएगा"):
    assert phrase in TEXT_A, f"label phrase changed: {phrase}"
JOBS = {  # name -> (text, speed)
    "A": (TEXT_A, 1.1),
    "B": (f"<shouting> {TEXT}", P["speed"]),  # the cached take
    "C_open": (OPEN, P["speed"]),
    "C_threat": (f"<shouting> {THREAT}", P["speed"]),
}
reqs = {k: al.uncached_requests(t, VOICE, P["language"], sp, 48000) for k, (t, sp) in JOBS.items()}
n_req, chars = sum(len(r) for r in reqs.values()), sum(sum(r) for r in reqs.values())
cost = round(chars * al.RUPEES_PER_CHAR, 2)
print(f"new TTS requests: {n_req} ({chars} characters), estimated cost Rs {cost}")
assert cost <= MAX_SPEND_INR, f"estimate Rs {cost} is above Rs {MAX_SPEND_INR}: stop and report"
if not RUN:
    raise SystemExit("measurement only (no MARYADA_RUN=1)")

# %% 3. Building blocks
client = httpx.Client(timeout=90)
cfg = voices_cfg["phone_chain"]


def tts(key: str) -> tuple[np.ndarray, int]:
    text, speed = JOBS[key]
    x, sr = al.synthesize(text, VOICE, P["language"], speed, 48000, client)
    return al.loudnorm(al.trim_silence(x, sr), sr, AGENT), sr


def shift(x: np.ndarray, sr: int, st: float) -> np.ndarray:
    """Pitch shift by `st` semitones, formants preserved (ffmpeg rubberband filter, quality mode)."""
    with tempfile.TemporaryDirectory() as d:
        src, dst = Path(d, "in.wav"), Path(d, "out.wav")
        sf.write(src, x, sr, subtype="PCM_16")
        al._ffmpeg(["-i", str(src), "-af", f"rubberband=pitch={2 ** (st / 12):.5f}:formant=preserved:pitchq=quality", "-ar", str(sr), str(dst)])
        return sf.read(dst, dtype="float32")[0]


def corrected(x: np.ndarray, sr: int, target: float) -> tuple[np.ndarray, float]:
    """Shift `x` so that the final phone version has the normal agent pitch; one refinement pass if still off by > 0.5 st."""
    st = 0.0
    for _ in range(2):
        y = shift(x, sr, st) if st else x
        ph = al.phone_voice(y, sr, target, cfg)
        gap = semitones(N_F0, median_f0(ph, 8000))
        if abs(gap) <= 0.5:
            break
        st += gap
    return ph, st


def presence_eq(x: np.ndarray, sr: int, f0: float = 2500.0, gain_db: float = 4.0, q: float = 0.9) -> np.ndarray:
    """RBJ peaking filter: a light presence boost around 2-3 kHz."""
    a_, w = 10 ** (gain_db / 40), 2 * np.pi * f0 / sr
    alpha = np.sin(w) / (2 * q)
    b = [1 + alpha * a_, -2 * np.cos(w), 1 - alpha * a_]
    a = [1 + alpha / a_, -2 * np.cos(w), 1 - alpha / a_]
    return signal.lfilter(b, a, x).astype(np.float32)


# %% 4. The three alternatives (all final phone audio, 8 kHz)
out: dict[str, np.ndarray] = {}
parts: dict[str, dict] = {}
xa, sr = tts("A")  # A: no tag, harder delivery; level and EQ after the phone chain
ph = al.compressor(presence_eq(al.phone_chain(xa, sr, cfg), 8000), 8000, -20.0, 2.0, 5.0, 80.0)
out["A"] = al.loudnorm(ph, 8000, SHOUT)
xb, sr = tts("B")  # B: the cached tagged take, pitch corrected
out["B"], st_b = corrected(xb, sr, SHOUT)
xo, sr = tts("C_open")  # C: plain opening + corrected tagged threat, joined with a short gap
open_ph = al.phone_voice(xo, sr, AGENT, cfg)
xt, sr = tts("C_threat")
threat_ph, st_c = corrected(xt, sr, SHOUT)
GAP_MS = 180
out["C"] = np.concatenate([open_ph, np.zeros(int(8000 * GAP_MS / 1000), dtype=np.float32), threat_ph])
parts["C"] = {"open": open_ph, "threat": threat_ph}
print("new TTS requests sent:", al.requests_made, "| pitch shift used: B", f"{st_b:+.1f}", "semitones, C", f"{st_c:+.1f}", "semitones (ffmpeg rubberband, formant=preserved)")

# %% 5. Measured figures against Prakash's normal turns
print(f"\n{'variant':14s} {'f0 Hz':>7s} {'vs normal':>10s} {'centre Hz':>10s} {'vs normal':>10s} {'LUFS':>6s} {'target':>7s} {'dBTP':>6s} {'dur s':>6s}  check")
rows = []
for name, x in {"current": phone_turns[5], **{k: v for k, v in out.items()}}.items():
    s = stats(x)
    measured = {"C": parts["C"]["threat"]}.get(name, x)
    m = al.measure_loudness(measured, 8000)
    d_st, d_c = semitones(s["f0"], N_F0), s["centre"] / N_CENTRE
    ok = abs(d_st) <= F0_TOL and d_c <= CENTRE_MAX and abs(m["lufs"] - SHOUT) <= 0.5 and m["true_peak"] <= -1.5
    rows.append((name, s, d_st, d_c, m, ok))
    print(f"{name:14s} {s['f0']:7.1f} {d_st:+9.1f}st {s['centre']:10.0f} {d_c * 100 - 100:+9.0f}% {m['lufs']:6.1f} {SHOUT:7.1f} {m['true_peak']:6.1f} {s['dur']:6.1f}  {'ok' if ok else 'CHECK'}")
m_open = al.measure_loudness(parts["C"]["open"], 8000)
print(f"C opening (plain): {m_open['lufs']:.1f} LUFS (target {AGENT:g}), {m_open['true_peak']:.1f} dBTP")

# %% 6. Variant files, call_X.mp3 and manifest_X.json (the current files are not touched), trio scenes
turn_nums = list(range(1, 10))
coach_x, c_sr = sf.read(AUD / "A4_coach_R5__Shubham__V2__raw.wav", dtype="float32")
chime = al.chime_at(al.target_lufs(voices_cfg, "coach"), c_sr)
gap = np.zeros(int(c_sr * 0.4), dtype=np.float32)
scene_files = []
for v, t5 in out.items():
    al.write_wav(DATA / "c06" / f"5_{v}.wav", t5, 8000)
    al.write_mp3(DATA / "c06" / f"5_{v}.mp3", t5, 8000, 64)
    seq = [t5 if i == 5 else phone_turns[i] for i in turn_nums]
    call, offsets = al.assemble_call(seq, 8000, "c06", gap_ms=tuple(cfg["turn_gap_ms"]))
    al.write_mp3(DATA / "c06" / f"call_{v}.mp3", call, 8000, 64)
    mf = json.loads(json.dumps(manifest))
    for t, off, a in zip(mf["turns"], offsets, seq, strict=True):
        t["offset_ms"], t["duration_ms"] = off, round(len(a) * 1000 / 8000)
        if t["idx"] == 5:
            t["wav8k"], t["mp3"] = f"c06/5_{v}.wav", f"c06/5_{v}.mp3"
    mf["call_mp3"], mf["duration_ms"] = f"c06/call_{v}.mp3", round(len(call) * 1000 / 8000)
    (DATA / "c06" / f"manifest_{v}.json").write_text(json.dumps({"c06": mf}, indent=1), encoding="utf-8")

    def up(x: np.ndarray) -> np.ndarray:
        return signal.resample_poly(x, c_sr, 8000).astype(np.float32)

    name = f"trio_c06_turn5_{v}__Prakash__Shivani_plain__Shubham_plain.wav"
    al.write_wav(AUD / name, np.concatenate([up(phone_turns[4]), gap, up(t5), gap, chime, coach_x, gap, up(phone_turns[6]), gap,
                                             up(phone_turns[7]), gap, up(phone_turns[8])]), c_sr)
    scene_files.append((v, name))
print("wrote variant files, manifests and", len(scene_files), "scenes")

# %% 7. INDEX: block "Hero call turn 5 alternatives"
what = {"A": "no tag; harder delivery (punctuation, speed 1.1, presence boost, light compression), +2.5 dB",
        "B": "existing tagged take, pitch shifted down to Prakash's normal pitch (formant preserved), +2.5 dB",
        "C": "plain opening words + tagged threat sentences as a separate pitch-corrected clip, 180 ms gap, +2.5 dB on the threat"}
head = "Hero call turn 5 alternatives"
md = ["", f"## {head}", "Current `call.mp3` is kept for comparison. Each `call_X.mp3` differs only in turn 5.", "", "- `../c06/call.mp3`: current (tagged take, high voice)"]
html = [f"<!--hero5alt--><h1>{head}</h1><p>Current call.mp3 is kept for comparison. Each call_X differs only in turn 5.</p>",
        "<p>Current call.mp3<br><audio controls preload=none src='../c06/call.mp3'></audio></p>"]
for v, scene in scene_files:
    md += [f"- `../c06/5_{v}.mp3`, `../c06/call_{v}.mp3`, `{scene}`: {what[v]}"]
    html += [f"<h3>{v}</h3><p>{what[v]}</p>", f"<p>turn 5 only<br><audio controls preload=none src='../c06/5_{v}.mp3'></audio></p>",
             f"<p>full call<br><audio controls preload=none src='../c06/call_{v}.mp3'></audio></p>",
             f"<p>scene (turns 4, 5, coach, 6, 7, 8)<br>{scene}<br><audio controls preload=none src='{scene}'></audio></p>"]
md_path, html_path = AUD / "INDEX.md", AUD / "INDEX.html"
md_path.write_text(md_path.read_text(encoding="utf-8").split(f"\n## {head}")[0] + "\n".join(md), encoding="utf-8")
html_path.write_text(html_path.read_text(encoding="utf-8").split("<!--hero5alt-->")[0] + "\n".join(html), encoding="utf-8")
print("INDEX updated:", html_path)
