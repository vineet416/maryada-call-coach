# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
# ---

# %% [markdown]
# # 01f Audition, voice-over with a wideband phone sound (gate G1)
# The voice-over line A8 (Shubham, V2) through the same kind of chain as the call audio (band-limit plus
# compressor), but wider than the 8 kHz phone line (16 kHz, 200-6500 Hz) so it reads as a clean wideband call
# and not as a narrow phone. No noise. Slightly lower level than the clean clip. Offline only, no TTS request.
# Run after `01e_audition_shout_prakash.py`.
# Run: `tools/.venv/Scripts/python notebooks/01f_audition_voiceover_room.py`

# %% Parameters
import sys
from pathlib import Path

import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import audio_lib as al

OUT = al.ROOT / "data" / "audio" / "_audition"
voices_cfg = al.load_yaml("content/voices.yaml")
CLEAN = -16.0  # level of the clean audition clip
DROP_LU = 2.0  # final voice-over level: voices.yaml loudness vo (-18 LUFS)
WIDE = voices_cfg["vo_chain"]  # same compressor as the call chain
SRC = OUT / "A8_voiceover__Shubham__V2__raw.wav"
DST = OUT / "A8_voiceover__Shubham__V2_wideband.wav"

# %% 1. Chain, then final loudness (the chain lowers the level)
x, sr = sf.read(SRC, dtype="float32")
y = al.phone_voice(x, sr, CLEAN - DROP_LU, WIDE)
al.write_wav(DST, y, WIDE["resample_hz"])

# %% 2. Check and INDEX
m = al.measure_loudness(y, WIDE["resample_hz"])
ok = abs(m["lufs"] - (CLEAN - DROP_LU)) <= 0.5 and m["true_peak"] <= -1.5
print(f"{DST.name}: clean {CLEAN:g} LUFS, now target {CLEAN - DROP_LU:g}, measured {m['lufs']:.1f} LUFS, "
      f"true peak {m['true_peak']:.1f} dBTP, {'ok' if ok else 'CHECK'}")

note = (f"Voice-over A8 (Shubham, V2) with a wideband phone sound (16 kHz, 200-6500 Hz, call compressor, no noise) at "
        f"{CLEAN - DROP_LU:g} LUFS (the clean clip is {CLEAN:g} LUFS).")
head = "\n## Round 2 voice-over wideband"
loud = (f"{head}\n\n| file | target LUFS | measured LUFS | LRA | true peak dBTP | check |\n|---|---|---|---|---|---|\n"
        f"| {DST.name} | {CLEAN - DROP_LU:g} | {m['lufs']:.1f} | {m['lra']:.1f} | {m['true_peak']:.1f} | {'ok' if ok else 'CHECK'} |")
for name, marker, add in (("LOUDNESS.md", head, loud), ("INDEX.md", head, f"{head}\n{note}\n- `{DST.name}`"),
                          ("INDEX.html", "<!--round2room-->",
                           (f"<!--round2room--><h2>Voice-over, wideband phone sound</h2><p>{note}<br>"
                            f"<audio controls preload=none src='{DST.name}'></audio></p>"))):
    path = OUT / name
    text = path.read_text(encoding="utf-8").split(marker)[0].split("\n## Round 2 voice-over room tone")[0]
    path.write_text(text + add, encoding="utf-8")
print("INDEX updated:", OUT / "INDEX.html")
