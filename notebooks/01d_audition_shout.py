# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
# ---

# %% [markdown]
# # 01d Audition, shouted threat line (gate G1)
# The hero turn 5 with the documented `shouting` tag at the very start of the text (so every word is covered), a
# check that the first second is as strong as the rest, and three gain variants (+2, +3.5, +5 dB above the plain
# agent level). Run after `01c_audition_tags.py`.
# Run: `tools/.venv/Scripts/python notebooks/01d_audition_shout.py` (add `MARYADA_RUN=1` to spend credits).

# %% Parameters
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
OUT = al.ROOT / "data" / "audio" / "_audition"
voices_cfg = al.load_yaml("content/voices.yaml")
c06 = next(s for s in al.load_yaml("content/scenarios/02_r3_abuse_threats.yaml")["scenarios"] if s["id"] == "c06")
TEXT = c06["turns"][4]["td"]  # turn 5 (agent threat) in Devanagari
AGENT = al.target_lufs(voices_cfg, "agent")
GAINS = {"V2T_plus2": 2.0, "V2T_plus3p5": 3.5, "V2T_plus5": 5.0}  # dB above the plain agent level
TAG = "shouting"  # documented for timbre-v3.0 (angle brackets, no closing tag, runs to the end of the text)
CLIP, VOICE = "A3_agent_threat", "Avinash"
p = voices_cfg["params"]["agent"]
JOB = {"clip": CLIP, "voice": VOICE, "var": "V2S", "text": f"<{TAG}> {TEXT.strip()}", "group": "agent",
       "lang": p["language"], "speed": p["speed"]}


# %% 1. Cost estimate (printed before anything is generated)
req = al.uncached_requests(JOB["text"], VOICE, JOB["lang"], JOB["speed"], 48000)
cost = round(sum(req) * al.RUPEES_PER_CHAR, 2)
print(f"new TTS requests: {len(req)} ({sum(req)} characters), estimated cost Rs {cost}")
print("text:", JOB["text"])
assert cost <= MAX_SPEND_INR, f"estimate Rs {cost} is above Rs {MAX_SPEND_INR}: stop and report"


# %% 2. Measuring helpers
def frames(x: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Time (s), momentary (400 ms) and short-term (3 s) loudness per 100 ms, from the ffmpeg ebur128 frame log."""
    with tempfile.TemporaryDirectory() as d:
        src = Path(d, "in.wav")
        sf.write(src, x, sr, subtype="PCM_16")
        log = al._ffmpeg(["-i", str(src), "-af", "ebur128=peak=true", "-f", "null", "-"])
    rows = re.findall(r"t:\s*([\d.]+)\s.*?M:\s*(-?[\d.]+)\s+S:\s*(-?[\d.]+)", log)
    t, m, s = (np.array([float(r[i]) for r in rows]) for i in range(3))
    return t, m, s


def peak_levels(x: np.ndarray, sr: int) -> dict[str, float]:
    t, m, s = frames(x, sr)
    full = s[t >= 3.0]  # before 3 s the short-term window is not filled yet
    return {"peak_short_term": float(full.max() if len(full) else s.max()), "peak_momentary": float(m.max()),
            "true_peak": al.measure_loudness(x, sr)["true_peak"]}


# %% 3. Generate (or load) the new take, then check the first second against the rest
client = httpx.Client(timeout=90)
A: dict[str, dict] = {}
files: list[dict] = []
if RUN:
    plain = al.render_clip({**JOB, "var": "V2", "text": TEXT}, OUT, voices_cfg, client)
    old = al.render_clip({**JOB, "var": "V2T", "text": ""}, OUT, voices_cfg, client)  # exists from 01c, never synthesised here
    new = al.render_clip(JOB, OUT, voices_cfg, client)
    files += [{"clip": CLIP, "voice": VOICE, "var": "V2S", "file": f, "kind": k, "target": AGENT,
               "note": "new take, tag at the very start, plain agent level"} for f, k in new["files"]]
    print("new TTS requests sent:", al.requests_made)

    x, sr = new["x"], new["sr"]  # raw (before the phone chain)
    first = al.measure_loudness(x[:sr], sr)["lufs"]
    rest = al.measure_loudness(x[sr:], sr)["lufs"]
    t, m, _ = frames(x, sr)
    print(f"RAW new take: first 1 s {first:.1f} LUFS, rest {rest:.1f} LUFS, difference {first - rest:+.1f} LU "
          f"(max momentary: first 1 s {m[t < 1.0].max():.1f}, rest {m[t >= 1.0].max():.1f} LUFS)")
    if first < rest - 2.0:
        raise SystemExit("first second is more than 2 LU below the rest: stop and report (no guessing about repeated tags)")

# %% 4. Level of the old V2T clip and the new take against the plain agent clip (phone files, as heard)
if RUN:
    lv = {"plain V2": peak_levels(plain["phone"], 8000), "old V2T": peak_levels(old["phone"], 8000),
          "new V2S": peak_levels(new["phone"], 8000)}
    for name, v in lv.items():
        print(f"{name:9s} peak short-term {v['peak_short_term']:.1f} LUFS | peak momentary {v['peak_momentary']:.1f} LUFS | "
              f"true peak {v['true_peak']:.1f} dBTP")
    for name in ("old V2T", "new V2S"):
        print(f"{name} peak short-term vs plain: {lv[name]['peak_short_term'] - lv['plain V2']['peak_short_term']:+.1f} dB; "
              f"peak momentary vs plain: {lv[name]['peak_momentary'] - lv['plain V2']['peak_momentary']:+.1f} dB")

# %% 5. Gain variants: gain applied after the phone chain (final loudness normalisation with the true-peak limiter)
V: dict[str, np.ndarray] = {}
if RUN:
    for var, gain in GAINS.items():
        target = AGENT + gain
        raw_f, phone_f = OUT / f"{CLIP}__{VOICE}__{var}__raw.wav", OUT / f"{CLIP}__{VOICE}__{var}__phone.wav"
        if not phone_f.exists():
            al.write_wav(raw_f, al.loudnorm(new["x"], new["sr"], target), new["sr"])
            al.write_wav(phone_f, al.phone_voice(new["x"], new["sr"], target, voices_cfg["phone_chain"]), 8000)
        V[var] = sf.read(phone_f, dtype="float32")[0]
        files += [{"clip": CLIP, "voice": VOICE, "var": var, "file": f.name, "kind": k, "target": target,
                   "note": f"shouted line {gain:+g} dB above the plain agent level"} for f, k in ((raw_f, "raw"), (phone_f, "phone"))]

# %% 6. Scenes (c) and (d) with the +3.5 dB variant
scene_files, scene_segments = [], {}
if RUN:
    def upsample(x: np.ndarray, rate: int) -> np.ndarray:
        return signal.resample_poly(x, rate, 8000).astype(np.float32)

    def load(clip: str, voice: str, var: str) -> np.ndarray:
        return sf.read(OUT / f"{clip}__{voice}__{var}__phone.wav", dtype="float32")[0]

    coach_x, c_sr = sf.read(OUT / "A4_coach_R5__Shubham__V2__raw.wav", dtype="float32")
    chime = al.chime_at(al.target_lufs(voices_cfg, "coach"), c_sr)
    gap = np.zeros(int(c_sr * 0.4), dtype=np.float32)
    SCENES = {"trio2c__Avinash_V2T_plus3p5__Shivani_V2T__Shubham_V2.wav": ("Shivani", "V2T"),
              "trio2d__Avinash_V2T_plus3p5__Chetana_V2__Shubham_V2.wav": ("Chetana", "V2")}
    for name, (b_voice, b_var) in SCENES.items():
        def b_line(clip: str, voice: str = b_voice, var: str = b_var) -> np.ndarray:
            return upsample(load(clip, voice, var), c_sr)

        parts = [("T4 borrower", b_line("A2_borrower_job"), -24.0),("T5 agent", upsample(V["V2T_plus3p5"], c_sr), AGENT + 3.5),
                 ("chime", chime, -27.0), ("coach", coach_x, -27.0), ("T6 borrower", b_line("H6_borrower_T6"), -24.0),
                 ("T7 agent", upsample(load("H7_agent_T7", VOICE, "V2"), c_sr), AGENT), ("T8 borrower", b_line("H8_borrower_T8"), -24.0)]
        seq = [parts[0][1], gap, parts[1][1], gap, chime, coach_x, gap, parts[4][1], gap, parts[5][1], gap, parts[6][1]]
        al.write_wav(OUT / name, np.concatenate(seq), c_sr)
        scene_files.append(name)
        scene_segments[name] = parts
    print("scenes:", scene_files)

# %% 7. Loudness table (section "Round 2 shout fix" in LOUDNESS.md): each file against its own target
if RUN:
    rows = []
    for f in files:
        x, sr = sf.read(OUT / f["file"], dtype="float32")
        rows.append((f["file"], f["target"], al.measure_loudness(x, sr), f["note"]))
    for name, segs in scene_segments.items():
        for seg, x, target in segs:
            probe = np.tile(x, 8) if seg == "chime" else x  # a chime is too short to measure alone
            rows.append((f"{name} / {seg}", target, al.measure_loudness(probe, c_sr), "same target as before" if "T5" not in seg else "shouted: own target"))
    lines = ["", "## Round 2 shout fix", "",
             ("The shouted clips intentionally sit above the agent level (-22 LUFS) and are exempt from the +-0.5 LU rule around -22; "
              "each must hit its own target (plain level +2 / +3.5 / +5 dB) within +-0.5 LU, true peak at or below -1.5 dBTP."), "",
             "| file | target LUFS | measured LUFS | LRA | true peak dBTP | check | note |", "|---|---|---|---|---|---|---|"]
    bad = 0
    for name, tgt, ms, note in rows:
        ok = abs(ms["lufs"] - tgt) <= 0.5 and ms["true_peak"] <= -1.5
        bad += not ok
        lines.append(f"| {name} | {tgt:g} | {ms['lufs']:.1f} | {ms['lra']:.1f} | {ms['true_peak']:.1f} | {'ok' if ok else 'CHECK'} | {note} |")
    path = OUT / "LOUDNESS.md"
    path.write_text(path.read_text(encoding="utf-8").split("\n## Round 2 shout fix")[0] + "\n".join(lines), encoding="utf-8")
    for name, tgt, ms, _ in rows:
        if "T5" in name or name.endswith("phone.wav") and "__V2" in name:
            print(f"{name}: target {tgt:g}, measured {ms['lufs']:.1f} LUFS, true peak {ms['true_peak']:.1f} dBTP")
    print("files outside their own +-0.5 LU target or above -1.5 dBTP:", bad)

# %% 8. INDEX: appended to the "Round 2 tags" section, next to the old V2T clip (kept for comparison)
if RUN:
    note = (f"Hero turn 5 with the shouting tag at the very start (every word covered). Old V2T = tag before the second sentence "
            f"(kept for comparison). Levels: plain agent {AGENT:g} LUFS; the variants are +2, +3.5 and +5 dB above it.")
    md = ["", "## Round 2 shout fix", note, ""]
    html = [f"<!--round2shout--><h2>Shouted threat line (fix)</h2><p>{note}</p>"]
    order = [("V2", "plain agent"), ("V2T", "old V2T (tag before sentence 2)"), ("V2S", "new take, plain level"),
             ("V2T_plus2", "new take +2 dB"), ("V2T_plus3p5", "new take +3.5 dB"), ("V2T_plus5", "new take +5 dB")]
    for var, label in order:
        for kind in ("phone", "raw"):
            fn = f"{CLIP}__{VOICE}__{var}__{kind}.wav"
            md.append(f"- `{fn}`: {label} / {kind}")
            html.append(f"<p>{label} / {kind}<br><audio controls preload=none src='{fn}'></audio></p>")
    scene_note = {"trio2c": "Scene (c) with the +3.5 dB shout: Avinash x Shivani (T4/T6/T8 tags) x Shubham plain.",
                  "trio2d": "Scene (d) with the +3.5 dB shout: Avinash x Chetana plain x Shubham plain."}
    md.append("")
    for name in scene_files:
        txt = scene_note[name.split("__")[0]]
        md.append(f"- `{name}`: {txt}")
        html.append(f"<p>{txt}<br>{name}<br><audio controls preload=none src='{name}'></audio></p>")
    md_path, html_path = OUT / "INDEX.md", OUT / "INDEX.html"
    md_path.write_text(md_path.read_text(encoding="utf-8").split("\n## Round 2 shout fix")[0] + "\n".join(md), encoding="utf-8")
    html_path.write_text(html_path.read_text(encoding="utf-8").split("<!--round2shout-->")[0] + "\n".join(html), encoding="utf-8")
    print("INDEX.md and INDEX.html updated:", html_path)
