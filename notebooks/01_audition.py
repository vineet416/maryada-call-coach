# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
# ---

# %% [markdown]
# # 01 Audition (gate G1)
# Generates the short audition clips, the trio test and an STT round trip.
# Open `data/audio/_audition/INDEX.html` (or `INDEX.md`) and listen. Then fill in the CHOICES cell at the end.
# Run: `tools/.venv/Scripts/python notebooks/01_audition.py` (add `MARYADA_RUN=1` to spend credits).

# %% Parameters
import json
import os
import sys
from pathlib import Path

import httpx2 as httpx
import numpy as np
import pandas as pd
import yaml
from scipy import signal

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import audio_lib as al

RUN = os.environ.get("MARYADA_RUN") == "1"  # nothing is sent to the TTS API unless this is set
STT = os.environ.get("MARYADA_STT") == "1"  # the STT round trip and stt_profile.yaml only run when this is set
PROBE = os.environ.get("MARYADA_PROBE") == "1"  # re-probe the TTS sample rates (spike result: 48 kHz is honoured)
MAX_SPEND_INR = 15
OUT = al.ROOT / "data" / "audio" / "_audition"
voices_cfg = al.load_yaml("content/voices.yaml")
audition = al.load_yaml("content/audition.yaml")
pd.set_option("display.width", 220, "display.max_colwidth", 70)

# %% 1. Environment, smoke request, sample rates
print("Gnani key:", al.mask(al.settings.gnani_api_key_id), "| Euri key:", al.mask(al.settings.euri_api_key))
client = httpx.Client(timeout=90)
SR = 48000
if RUN and PROBE:
    rates = al.probe_sample_rates(client)
    print("sample rates (requested -> returned):", rates)
    honoured = [r for r, got in rates.items() if got == r and r >= 16000]
    SR = max(honoured) if honoured else 16000
print("Working sample rate:", SR)

# %% 2. Jobs: clip x voice x variant (+ the trio voices)
ROLE_GROUP = {"agent": "agent", "borrower": "borrower", "spouse": "third_party", "neighbour": "third_party",
              "coach": "coach", "vo": "vo"}
PARAM_KEY = {"agent": "agent", "borrower": "borrower", "third_party": "third", "coach": "coach", "vo": "vo"}
trio = audition["trio"]


def group_of(role: str) -> str:
    return ROLE_GROUP[role.split("_")[0]]


def target_lufs(group: str) -> float:
    return float(str(voices_cfg["loudness"][group]).split()[0])


jobs = []
for clip in audition["clips"]:
    voices = list(clip["voices"])
    if clip["id"] == "A3_agent_threat":
        voices += [v for v in trio["agents"] if v not in voices]  # the trio needs both agents on this line
    for voice in voices:
        for var, text in clip["variants"].items():
            if voice not in clip["voices"] and var != "V1":
                continue
            group = group_of(clip["role"])
            lang = "mr-IN" if var == "V3" else voices_cfg["params"][PARAM_KEY[group]]["language"]
            jobs.append({"clip": clip["id"], "role": clip["role"], "group": group, "voice": voice, "var": var,
                         "text": text, "lang": lang, "speed": voices_cfg["params"][PARAM_KEY[group]]["speed"]})
chars, inr = al.credit_estimate([j["text"] for j in jobs])
print(f"{len(jobs)} clips, {chars} characters, estimated cost Rs {inr}")
assert inr < MAX_SPEND_INR, "audition would cost too much"

# %% 3. Generate raw (loudness-normalised, full band) and phone versions
raw_audio, phone_audio, files = {}, {}, []
if RUN:
    OUT.mkdir(parents=True, exist_ok=True)
    for j in jobs:
        key = (j["clip"], j["voice"], j["var"])
        x, sr = al.synthesize(j["text"], j["voice"], j["lang"], j["speed"], SR, client)
        target = target_lufs(j["group"])
        x = al.loudnorm(al.trim_silence(x, sr), sr, target)
        raw_audio[key] = (x, sr)
        stem = f"{j['clip']}__{j['voice']}__{j['var']}"
        al.write_wav(OUT / f"{stem}__raw.wav", x, sr)
        files.append({**j, "file": f"{stem}__raw.wav", "kind": "raw"})
        if j["group"] in ("agent", "borrower", "third_party"):
            p = al.phone_voice(x, sr, target, voices_cfg["phone_chain"])  # final loudness AFTER the phone chain
            phone_audio[key] = p
            al.write_wav(OUT / f"{stem}__phone.wav", p, 8000)
            files.append({**j, "file": f"{stem}__phone.wav", "kind": "phone"})
    print("generated", len(files), "files in", OUT)

# %% 4. Trio test: borrower -> agent -> earcon -> coach, 2 agents x 2 coaches
trio_files = []
trio_segments = {}


def upsample(p: np.ndarray, sr: int) -> np.ndarray:
    return signal.resample_poly(p, sr, 8000).astype(np.float32)


if RUN:
    b_phone = phone_audio[("A2_borrower_job", trio["borrowers"][0], "V1")]
    for agent in trio["agents"]:
        for coach in trio["coaches"]:
            c, c_sr = raw_audio[("A4_coach_R5", coach, "V1")]
            chime = al.chime_at(target_lufs("coach"), c_sr)
            gap = np.zeros(int(c_sr * 0.4), dtype=np.float32)
            threat = phone_audio[("A3_agent_threat", agent, "V1")]
            parts = [("borrower", upsample(b_phone, c_sr), "borrower"), ("agent", upsample(threat, c_sr), "agent"),
                     ("chime", chime, "coach"), ("coach", c, "coach")]
            scene = np.concatenate([parts[0][1], gap, parts[1][1], gap, chime, c])
            trio_segments[f"trio__{agent}__{coach}.wav"] = [(n, a, g) for n, a, g in parts]
            name = f"trio__{agent}__{coach}.wav"
            al.write_wav(OUT / name, scene, c_sr)
            trio_files.append(name)
    print("trio scenes:", trio_files)

# %% 5. Loudness table (ebur128 on the finished files)
loud_rows = []
if RUN:
    import soundfile as sf

    for f in files:
        x, sr = sf.read(OUT / f["file"], dtype="float32")
        loud_rows.append((f["file"], target_lufs(f["group"]), al.measure_loudness(x, sr)))
    for name, segs in trio_segments.items():
        for seg, x, group in segs:
            probe = np.tile(x, 8) if seg == "chime" else x  # a chime is too short to measure alone
            loud_rows.append((f"{name} / {seg}", target_lufs(group), al.measure_loudness(probe, c_sr)))
    lines = ["# Loudness of the finished files (ffmpeg ebur128)", "",
             "| file | target LUFS | measured LUFS | LRA | true peak dBTP | check |", "|---|---|---|---|---|---|"]
    for name, tgt, m in loud_rows:
        ok = abs(m["lufs"] - tgt) <= 0.5 and m["true_peak"] <= -1.5
        lines.append(f"| {name} | {tgt:g} | {m['lufs']:.1f} | {m['lra']:.1f} | {m['true_peak']:.1f} | {'ok' if ok else 'CHECK'} |")
    (OUT / "LOUDNESS.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(l for l in lines if "CHECK" in l or l.startswith(("| file", "|---"))))
    for tgt in sorted({t for _, t, _ in loud_rows}):
        ms = [m for _, t, m in loud_rows if t == tgt]
        print(f"target {tgt:g} LUFS: {len(ms)} files, measured {min(m['lufs'] for m in ms):.1f} to "
              f"{max(m['lufs'] for m in ms):.1f}, highest true peak {max(m['true_peak'] for m in ms):.1f} dBTP")
    for name, tgt, m in loud_rows:
        if name.startswith("trio__Avinash__Shubham"):
            print(f"  {name}: {m['lufs']:.1f} LUFS (target {tgt:g}), true peak {m['true_peak']:.1f}")
    print("files outside +-0.5 LU or above -1.5 dBTP:", sum("CHECK" in l for l in lines))

# %% 6. Index for listening
if RUN:
    notes = {c["id"]: c["note"] for c in audition["clips"]}
    md = ["# Audition index", "", "Open the .wav files directly or open INDEX.html. `raw` = clean voice, `phone` = as heard on the call.",
          "Loudness of every file: LOUDNESS.md.", ""]
    html = ["<meta charset=utf-8><title>Audition</title><body style='font-family:sans-serif;max-width:900px;margin:2em auto'><h1>Audition</h1><p><a href='LOUDNESS.md'>Loudness table</a></p>"]
    for cid, note in notes.items():
        md += [f"## {cid}", note, ""]
        html += [f"<h2>{cid}</h2><p>{note}</p>"]
        for f in [f for f in files if f["clip"] == cid]:
            label = f"{f['voice']} / {f['var']} / {f['kind']}"
            md.append(f"- `{f['file']}`: {label}")
            html.append(f"<p>{label}<br><audio controls preload=none src='{f['file']}'></audio></p>")
        md.append("")
    md += ["## Trio test", "Borrower, then agent threat, then chime and coach. Pick the combination where the three voices are easiest to tell apart.", ""]
    html.append("<h2>Trio test</h2><p>Borrower, agent threat, chime, coach. Pick the most distinct combination.</p>")
    for name in trio_files:
        md.append(f"- `{name}`")
        html.append(f"<p>{name}<br><audio controls preload=none src='{name}'></audio></p>")
    (OUT / "INDEX.md").write_text("\n".join(md), encoding="utf-8")
    (OUT / "INDEX.html").write_text("\n".join(html), encoding="utf-8")
    print("wrote INDEX.md and INDEX.html")

# %% 7. STT round trip (REST for all phone clips, realtime for one clip)
COMBOS = {"A indic-auto": {"language_code": "indic-auto", "multi_lang_codes": "hi-IN,mr-IN,en-IN"},
          "B indic-auto hi,en": {"language_code": "indic-auto", "multi_lang_codes": "hi-IN,en-IN"},
          "C hi-IN": {"language_code": "hi-IN"}, "D mr-IN": {"language_code": "mr-IN"}}
hints = audition["stt_roundtrip"]["key_terms_hint"]
v1_text = {c["id"]: c["variants"]["V1"] for c in audition["clips"]}
rows = []
if RUN and STT:
    al.spike.HINTS[:] = hints
    for f in [f for f in files if f["kind"] == "phone"]:
        terms = al.key_terms(v1_text[f["clip"]])
        combos = {k: v for k, v in COMBOS.items() if not (k.startswith("D") and f["group"] == "agent")}
        res = al.stt_roundtrip(OUT / f["file"], combos)
        for name, (text, latency, lang) in res.items():
            ok = not text.startswith("ERROR")
            rows.append({"clip": f["clip"], "voice": f["voice"], "var": f["var"], "group": f["group"], "combo": name,
                         "recovery": round(al.recovery(terms, text), 2) if ok else None,
                         "lang": lang, "latency_s": round(latency, 2), "text": text[:70]})
    df = pd.DataFrame(rows)
    print(df.drop(columns=["group"]).to_string(index=False))
    summary = df.groupby(["group", "combo"])["recovery"].mean().round(3).unstack()
    print("\nMean keyword recovery per role group and setting:\n", summary)
    print("\nBy text variant (V1 Roman, V2 Devanagari, V3 Roman + mr-IN, TAG tagged):\n",
          df.groupby(["group", "var", "combo"])["recovery"].mean().round(2).unstack())
    df.to_csv(OUT / "stt_roundtrip.csv", index=False)

# %% 8. Realtime check on one clip and write content/stt_profile.yaml
if RUN and STT:
    sample = OUT / "A3_agent_threat__Avinash__V1__phone.wav"
    rt = {}
    for name, (lang, cand) in {"A indic-auto": ("indic-auto", None), "B indic-auto+candidates": ("indic-auto", "hi,mr,en"),
                               "C hi-IN": ("hi-IN", None)}.items():
        text, lats, _ = al.stt_realtime(sample, lang, cand)
        rt[name] = {"ok": not text.startswith("ERROR"), "segment_latency_s": round(float(np.median(lats)), 3) if lats else None}
    print("realtime:", rt)
    order = ["C hi-IN", "B indic-auto hi,en", "A indic-auto", "D mr-IN"]  # simplest first on ties
    profile = {"model": "prisma-v3.0", "adapter_default": "realtime" if all(v["ok"] for v in rt.values()) else "rest",
               "selected_by": "mean keyword recovery on the audition clips (tools/audio_lib.py scoring)"}
    for group, key in (("agent", "agent"), ("borrower", "borrower"), ("third_party", "third_party")):
        best = max(order, key=lambda c: (summary.loc[group].get(c, -1) if group in summary.index else -1, -order.index(c)))
        profile[key] = dict(COMBOS[best])
        profile[key]["setting"] = best
    (al.ROOT / "content" / "stt_profile.yaml").write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")
    print("wrote content/stt_profile.yaml:", json.dumps(profile))

# %% 9. CHOICES (edit after listening; set CONFIRMED = True to write content/tts_profile.yaml)
# The values below are only the recommendation from content/voices.yaml. They are NOT applied until the user answers.
CONFIRMED = False
CHOICES = {
    "agent_m1": "Prakash", "agent_m2": "Avinash", "agent_f1": "Shivani", "agent_f2": "Lakshmi",
    "borrower_m1": "Devansh", "borrower_m2": "Yashraj", "borrower_f": "Chetana", "spouse_f": "Chetana",
    "neighbour_m": "Shubham", "coach": "Kalpana", "vo": "Kalpana",
    "text_mode": {"agent": "roman", "borrower": "roman", "third_party": "roman", "coach": "roman", "vo": "roman"},
    "language": {"agent": "hi-IN", "borrower": "hi-IN", "third_party": "hi-IN", "coach": "hi-IN", "vo": "en-IN"},
    "use_tags": False,
}
if CONFIRMED:
    (al.ROOT / "content" / "tts_profile.yaml").write_text(yaml.safe_dump(CHOICES, sort_keys=False), encoding="utf-8")
    print("wrote content/tts_profile.yaml")
else:
    print("CHOICES not applied (waiting for the user's answer at gate G1)")
