# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
# ---

# %% [markdown]
# # 01c Audition, tagged clips (gate G1)
# Devanagari (`V2`) text plus ONE documented Timbre v3.0 audio tag (`V2T`), next to the plain V2 clips, and two longer
# hero scenes (agent tag only, and agent + borrower tags). Run after `01_audition.py` and `01b_audition_round2.py`.
# Run: `tools/.venv/Scripts/python notebooks/01c_audition_tags.py` (add `MARYADA_RUN=1` to spend credits).

# %% Parameters
import os
import re
import sys
from pathlib import Path

import httpx2 as httpx
import numpy as np
import soundfile as sf
from scipy import signal

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import audio_lib as al

RUN = os.environ.get("MARYADA_RUN") == "1"
MAX_SPEND_INR = 40
OUT = al.ROOT / "data" / "audio" / "_audition"
voices_cfg = al.load_yaml("content/voices.yaml")
audition = al.load_yaml("content/audition.yaml")
clips = {c["id"]: c for c in audition["clips"]}
c06 = next(s for s in al.load_yaml("content/scenarios/02_r3_abuse_threats.yaml")["scenarios"] if s["id"] == "c06")
td = {n: c06["turns"][n - 1]["td"] for n in range(1, 10)}  # c06 turns in Devanagari
PARAM_KEY = {"agent": "agent", "borrower": "borrower", "third_party": "third", "coach": "coach", "vo": "vo"}

# Tags documented for timbre-v3.0 (docs.gnani.ai, audio tags): angle brackets, no closing tag, lower case.
# Anything else is stripped silently by the API, so it must never be used.
DOCUMENTED_TAGS = {"laugh", "giggle", "sigh", "exhales", "sniffles", "yawns", "coughs", "clears throat", "whispers",
                   "shouting", "excited", "slow", "pauses"}


def tagged(text: str, tag: str, before_sentence: int = 0) -> str:
    """Insert `<tag>` in front of sentence number `before_sentence` (0 = start). The effect runs to the end of the text."""
    assert tag in DOCUMENTED_TAGS, f"{tag!r} is not a documented tag"
    sentences = re.split(r"(?<=[.!?।])\s+", text.strip())
    sentences[before_sentence] = f"<{tag}> {sentences[before_sentence]}"
    return " ".join(sentences)


def job(clip: str, voice: str, var: str, text: str, group: str) -> dict:
    p = voices_cfg["params"][PARAM_KEY[group]]
    return {"clip": clip, "voice": voice, "var": var, "text": text, "group": group, "lang": p["language"], "speed": p["speed"]}


# %% 1. Jobs and the cost estimate (printed before anything is generated)
a6 = clips["A6_male_borrower"]["variants"]["V2"]
TAGGED = [  # (clip, voice, group, plain text, tagged text)
    job("A3_agent_threat", "Avinash", "V2T", tagged(td[5], "shouting", 1), "agent"),
    job("A2_borrower_job", "Shivani", "V2T", tagged(td[4], "sigh"), "borrower"),
    job("H6_borrower_T6", "Shivani", "V2T", tagged(td[6], "sniffles", 1), "borrower"),
    job("H8_borrower_T8", "Shivani", "V2T", tagged(td[8], "sigh"), "borrower"),
    job("A6_male_borrower", "Yashraj", "V2T", tagged(a6, "sigh"), "borrower"),
]
PLAIN = [  # pairs of the tagged clips and the extra lines the longer scenes need
    job("A3_agent_threat", "Avinash", "V2", td[5], "agent"),
    job("A2_borrower_job", "Shivani", "V2", td[4], "borrower"),
    job("H6_borrower_T6", "Shivani", "V2", td[6], "borrower"),
    job("H8_borrower_T8", "Shivani", "V2", td[8], "borrower"),
    job("A6_male_borrower", "Yashraj", "V2", a6, "borrower"),
    job("A2_borrower_job", "Chetana", "V2", td[4], "borrower"),
    job("H6_borrower_T6", "Chetana", "V2", td[6], "borrower"),
    job("H8_borrower_T8", "Chetana", "V2", td[8], "borrower"),
    job("H7_agent_T7", "Avinash", "V2", td[7], "agent"),
    job("A4_coach_R5", "Shubham", "V2", clips["A4_coach_R5"]["variants"]["V2"], "coach"),
]
for j in TAGGED:
    assert "angry" not in j["text"], "undocumented tag"


def needs(jobs: list[dict]) -> tuple[int, int]:
    n = [al.uncached_requests(j["text"], j["voice"], j["lang"], j["speed"], 48000) for j in jobs]
    return sum(len(x) for x in n), sum(sum(x) for x in n)


t_req, t_chars = needs(TAGGED)
p_req, p_chars = needs(PLAIN)
cost = round((t_chars + p_chars) * al.RUPEES_PER_CHAR, 2)
print(f"V2T (tagged) TTS requests: {t_req} ({t_chars} characters); plain V2 requests (control and scene lines): {p_req} "
      f"({p_chars} characters); estimated cost Rs {cost}")
for j in TAGGED:
    print(f"  {j['clip']:18s} {j['voice']:9s} {j['var']:4s} {j['text'][:60]}")
assert cost <= MAX_SPEND_INR, f"estimate Rs {cost} is above Rs {MAX_SPEND_INR}: stop and report"

# %% 2. Generate or load
client = httpx.Client(timeout=90)
A: dict[tuple[str, str, str], dict] = {}
files = []
if RUN:
    for j in PLAIN + TAGGED:
        r = al.render_clip(j, OUT, voices_cfg, client)
        A[(j["clip"], j["voice"], j["var"])] = r
        files += [{**j, "new": r["new"], "file": f, "kind": k} for f, k in r["files"]]
    print("new clip files:", sum(f["new"] for f in files), "| new TTS requests:", al.requests_made)


# %% 3. Scenes of the hero call: T4, T5 (agent), chime + coach, T6, T7 (agent), T8
def upsample(p: np.ndarray, sr: int) -> np.ndarray:
    return signal.resample_poly(p, sr, 8000).astype(np.float32)


scene_files, scene_segments = [], {}
SCENES = {  # name -> (agent T5 variant, borrower voice, borrower variant)
    "trio2c__Avinash_V2T__Shivani_V2T__Shubham_V2.wav": ("V2T", "Shivani", "V2T"),
    "trio2d__Avinash_V2T__Chetana_V2__Shubham_V2.wav": ("V2T", "Chetana", "V2"),
}
if RUN:
    coach = A[("A4_coach_R5", "Shubham", "V2")]
    c_sr = coach["sr"]
    chime = al.chime_at(al.target_lufs(voices_cfg, "coach"), c_sr)
    gap = np.zeros(int(c_sr * 0.4), dtype=np.float32)
    for name, (agent_var, b_voice, b_var) in SCENES.items():
        def b_line(clip: str, var: str, voice: str = b_voice) -> np.ndarray:
            return upsample(A[(clip, voice, var)]["phone"], c_sr)

        t5 = upsample(A[("A3_agent_threat", "Avinash", agent_var)]["phone"], c_sr)
        t7 = upsample(A[("H7_agent_T7", "Avinash", "V2")]["phone"], c_sr)
        parts = [("T4 borrower", b_line("A2_borrower_job", b_var), "borrower"), ("T5 agent", t5, "agent"),
                 ("chime", chime, "coach"), ("coach", coach["x"], "coach"),
                 ("T6 borrower", b_line("H6_borrower_T6", b_var), "borrower"), ("T7 agent", t7, "agent"),
                 ("T8 borrower", b_line("H8_borrower_T8", b_var), "borrower")]
        seq = [parts[0][1], gap, parts[1][1], gap, chime, coach["x"], gap, parts[4][1], gap, parts[5][1], gap, parts[6][1]]
        al.write_wav(OUT / name, np.concatenate(seq), c_sr)
        scene_files.append(name)
        scene_segments[name] = parts
    print("scenes:", scene_files)

# %% 4. Loudness check and table (appended to LOUDNESS.md as "Round 2 tags")
if RUN:
    rows = []
    for f in files:
        x, sr = sf.read(OUT / f["file"], dtype="float32")
        rows.append((f["file"], al.target_lufs(voices_cfg, f["group"]), al.measure_loudness(x, sr)))
    for name, segs in scene_segments.items():
        for seg, x, group in segs:
            probe = np.tile(x, 8) if seg == "chime" else x  # a chime is too short to measure alone
            rows.append((f"{name} / {seg}", al.target_lufs(voices_cfg, group), al.measure_loudness(probe, c_sr)))
    lines = ["", "## Round 2 tags", "", "| file | target LUFS | measured LUFS | LRA | true peak dBTP | check |", "|---|---|---|---|---|---|"]
    bad = 0
    for name, tgt, m in rows:
        ok = abs(m["lufs"] - tgt) <= 0.5 and m["true_peak"] <= -1.5
        bad += not ok
        lines.append(f"| {name} | {tgt:g} | {m['lufs']:.1f} | {m['lra']:.1f} | {m['true_peak']:.1f} | {'ok' if ok else 'CHECK'} |")
    path = OUT / "LOUDNESS.md"
    path.write_text(path.read_text(encoding="utf-8").split("\n## Round 2 tags")[0] + "\n".join(lines), encoding="utf-8")
    for tgt in sorted({t for _, t, _ in rows}):
        ms = [m for _, t, m in rows if t == tgt]
        print(f"target {tgt:g} LUFS: {len(ms)} files, measured {min(m['lufs'] for m in ms):.1f} to "
              f"{max(m['lufs'] for m in ms):.1f}, highest true peak {max(m['true_peak'] for m in ms):.1f} dBTP")
    print("round 2 tags files outside +-0.5 LU or above -1.5 dBTP:", bad)

# %% 5. INDEX: "Round 2 tags" section, each tagged clip next to its plain V2 clip
if RUN:
    PAIRS = [
        ("A3_agent_threat", "Avinash", "Hero turn 5: plain V2, and V2T with the shouting tag before the threat sentence (it runs to the end of the turn)."),
        ("A2_borrower_job", "Shivani", "Hero turn 4: plain V2, and V2T with a sigh tag at the start."),
        ("H6_borrower_T6", "Shivani", "Hero turn 6: plain V2, and V2T with a sniffles tag before the second sentence."),
        ("H8_borrower_T8", "Shivani", "Hero turn 8: plain V2, and V2T with a sigh tag at the start."),
        ("A6_male_borrower", "Yashraj", "Male borrower: plain V2, and V2T with a sigh tag at the start."),
    ]
    md = ["", "## Round 2 tags", "Tags used (all documented for timbre-v3.0): shouting, sigh, sniffles. No tags on Prakash, Shubham or the voice-over.", ""]
    html = ["<!--round2tags--><h1>Round 2 tags</h1><p>Tags used (all documented): shouting, sigh, sniffles. Loudness: LOUDNESS.md, section Round 2 tags.</p>"]
    for clip, voice, note in PAIRS:
        md += [f"### {clip}", note]
        html += [f"<h3>{clip}</h3><p>{note}</p>"]
        for var in ("V2", "V2T"):
            for f in [f for f in files if f["clip"] == clip and f["voice"] == voice and f["var"] == var]:
                label = f"{voice} / {var} / {f['kind']}"
                md.append(f"- `{f['file']}`: {label}")
                html.append(f"<p>{label}<br><audio controls preload=none src='{f['file']}'></audio></p>")
        md.append("")
    scene_note = {"trio2c": "Scene (c): Avinash with the shouting tag x Shivani with the T4/T6/T8 tags x Shubham plain.",
                  "trio2d": "Scene (d): the same agent tag, but Chetana plain V2 as the borrower (judge the agent tag separately)."}
    md += ["### Hero scenes (turns 4, 5, coach, 6, 7, 8)"]
    html += ["<h3>Hero scenes (turns 4, 5, coach, 6, 7, 8)</h3>"]
    for name in scene_files:
        note = scene_note[name.split("__")[0]]
        md.append(f"- `{name}`: {note}")
        html.append(f"<p>{note}<br>{name}<br><audio controls preload=none src='{name}'></audio></p>")
    md_path, html_path = OUT / "INDEX.md", OUT / "INDEX.html"
    md_path.write_text(md_path.read_text(encoding="utf-8").split("\n## Round 2 tags")[0] + "\n".join(md), encoding="utf-8")
    html_path.write_text(html_path.read_text(encoding="utf-8").split("<!--round2tags-->")[0] + "\n".join(html), encoding="utf-8")
    print("INDEX.md and INDEX.html updated:", html_path)
