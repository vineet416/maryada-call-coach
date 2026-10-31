# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
# ---

# %% [markdown]
# # 01f Audition, voice-over with a little room tone (gate G1)
# The voice-over line A8 (Shubham, V2) with very quiet pink noise under it and a slightly lower level than the clean
# clip. Offline only, no TTS request. Run after `01e_audition_shout_prakash.py`.
# Run: `tools/.venv/Scripts/python notebooks/01f_audition_voiceover_room.py`

# %% Parameters
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import audio_lib as al

OUT = al.ROOT / "data" / "audio" / "_audition"
voices_cfg = al.load_yaml("content/voices.yaml")
CLEAN = al.target_lufs(voices_cfg, "vo")  # level of the clean voice-over (-16 LUFS)
DROP_LU = 2.0  # "a little lower" than the clean clip
SNR_DB = 35.0  # speech to noise; quiet enough to read as room tone, not hiss
SRC = OUT / "A8_voiceover__Shubham__V2__raw.wav"
DST = OUT / "A8_voiceover__Shubham__V2_room__raw.wav"


# %% 1. Mix and normalise
def pink_noise(n: int, sr: int, rng: np.random.Generator) -> np.ndarray:
    """1/f noise from white noise, with a 80 Hz high-pass so there is no rumble."""
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / sr)
    spec[1:] /= np.sqrt(f[1:])
    spec[0] = 0
    x = np.fft.irfft(spec, n)
    return signal.sosfilt(signal.butter(2, 80, btype="highpass", fs=sr, output="sos"), x).astype(np.float32)


x, sr = sf.read(SRC, dtype="float32")
speech_rms = float(np.sqrt(np.mean(x[np.abs(x) > 0.02 * np.abs(x).max()] ** 2)))  # level while speaking
noise = pink_noise(len(x), sr, np.random.default_rng(7))
noise *= speech_rms * 10 ** (-SNR_DB / 20) / float(np.sqrt(np.mean(noise**2)))
y = al.loudnorm(x + noise, sr, CLEAN - DROP_LU)
al.write_wav(DST, y, sr)

# %% 2. Check and INDEX
m = al.measure_loudness(y, sr)
ok = abs(m["lufs"] - (CLEAN - DROP_LU)) <= 0.5 and m["true_peak"] <= -1.5
print(f"{DST.name}: clean {CLEAN:g} LUFS, now target {CLEAN - DROP_LU:g}, measured {m['lufs']:.1f} LUFS, "
      f"true peak {m['true_peak']:.1f} dBTP, noise {SNR_DB:g} dB below the speech, {'ok' if ok else 'CHECK'}")

note = (f"Voice-over A8 (Shubham, V2) with quiet pink room tone ({SNR_DB:g} dB below the speech) at {CLEAN - DROP_LU:g} LUFS "
        f"(the clean clip is {CLEAN:g} LUFS).")
loud = (f"\n## Round 2 voice-over room tone\n\n| file | target LUFS | measured LUFS | LRA | true peak dBTP | check |\n|---|---|---|---|---|---|\n"
        f"| {DST.name} | {CLEAN - DROP_LU:g} | {m['lufs']:.1f} | {m['lra']:.1f} | {m['true_peak']:.1f} | {'ok' if ok else 'CHECK'} |")
for name, marker, add in (("LOUDNESS.md", "\n## Round 2 voice-over room tone", loud),
                          ("INDEX.md", "\n## Round 2 voice-over room tone", f"\n## Round 2 voice-over room tone\n{note}\n- `{DST.name}`"),
                          ("INDEX.html", "<!--round2room-->",
                           f"<!--round2room--><h2>Voice-over with room tone</h2><p>{note}<br><audio controls preload=none src='{DST.name}'></audio></p>")):
    path = OUT / name
    path.write_text(path.read_text(encoding="utf-8").split(marker)[0] + add, encoding="utf-8")
print("INDEX updated:", OUT / "INDEX.html")
