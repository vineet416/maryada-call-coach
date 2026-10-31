# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
# ---

# %% [markdown]
# # 03 Noise conditions (evaluation only)
# Every call turn from the raw full-band WAVs gets pink noise plus speech babble (mixed 1:1 in power), scaled to an SNR of
# 20, 10 and 5 dB, then the same phone chain as the clean audio. Output: `data/eval/audio/<cond>/<id>/<idx>.wav`
# (git-ignored, regenerable, no TTS credits). Run: `tools/.venv/Scripts/python -X utf8 notebooks/03_noise.py`.

# %% Parameters
import json
import sys
import zlib
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import audio_lib as al

CONDITIONS = {"snr20": 20, "snr10": 10, "snr5": 5}
TOLERANCE_DB = 0.5
DATA = al.ROOT / "data" / "audio"
OUT = al.ROOT / "data" / "eval" / "audio"
voices_cfg = al.load_yaml("content/voices.yaml")
manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
raw_files = {sid: sorted((DATA / "raw" / sid).glob("*.wav")) for sid in manifest if (DATA / "raw" / sid).exists()}
missing = sorted(set(manifest) - set(raw_files))
print(f"scenarios with raw audio: {len(raw_files)}; without (skipped): {missing or 'none'}")


# %% Helpers
def speech_power(x: np.ndarray, sr: int) -> float:
    """Mean power over the speech-active frames: 20 ms frames within 40 dB of the file's loudest frame."""
    n = int(sr * 0.02)
    frames = x[: len(x) // n * n].reshape(-1, n)
    rms = np.sqrt(np.mean(frames**2, axis=1) + 1e-12)
    active = 20 * np.log10(rms) > 20 * np.log10(rms.max()) - 40
    return float(np.mean(frames[active] ** 2))


def pink(n: int, rng: np.random.Generator) -> np.ndarray:
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.arange(len(spec), dtype=float)
    f[0] = 1.0
    y = np.fft.irfft(spec / np.sqrt(f), n)
    return y / np.sqrt(np.mean(y**2))


def babble(sid: str, n: int, sr: int, rng: np.random.Generator) -> np.ndarray:
    """4 or 5 clips of OTHER calls, low-passed to the speech band, placed at random offsets, summed."""
    others = [p for s, ps in raw_files.items() if s != sid for p in ps]
    sos = signal.butter(4, 4000, btype="lowpass", fs=sr, output="sos")
    total = np.zeros(n)
    for k in rng.choice(len(others), size=int(rng.integers(4, 6)), replace=False):
        clip, csr = sf.read(others[k], dtype="float32")
        assert csr == sr
        clip = signal.sosfilt(sos, np.resize(clip, n))
        total += np.roll(clip, int(rng.integers(0, n)))
    return total / np.sqrt(np.mean(total**2))


def noisy(x: np.ndarray, sr: int, sid: str, cond: str, snr_db: int) -> tuple[np.ndarray, float]:
    rng = np.random.default_rng(42 + zlib.crc32(f"{sid}/{cond}".encode()))
    n = len(x)
    noise = np.sqrt(0.5) * pink(n, rng) + np.sqrt(0.5) * babble(sid, n, sr, rng)  # 1:1 in power
    noise *= np.sqrt(speech_power(x, sr) / 10 ** (snr_db / 10)) / np.sqrt(np.mean(noise**2))
    achieved = 10 * np.log10(speech_power(x, sr) / np.mean(noise**2))
    return (x + noise).astype(np.float32), float(achieved)


# %% Build: mix on the full-band raw signal, then the same phone chain (8 kHz, band-pass, compressor)
rows, problems = [], []
for sid, files in raw_files.items():
    for f in files:
        x, sr = sf.read(f, dtype="float32")
        for cond, snr in CONDITIONS.items():
            mix, achieved = noisy(x, sr, sid, cond, snr)
            if abs(achieved - snr) > TOLERANCE_DB:
                problems.append(f"{sid}/{f.stem} {cond}: SNR {achieved:.2f}")
            dest = OUT / cond / sid / f"{f.stem}.wav"
            al.write_wav(dest, al.phone_chain(mix, sr, voices_cfg["phone_chain"]), voices_cfg["phone_chain"]["resample_hz"])
            rows.append((cond, achieved))

# %% Check: files and the achieved SNR per condition
for cond, snr in CONDITIONS.items():
    a = np.array([r[1] for r in rows if r[0] == cond])
    n_files = sum(1 for _ in (OUT / cond).glob("*/*.wav"))
    print(f"{cond}: {n_files} files, achieved SNR min {a.min():.2f} / mean {a.mean():.2f} / max {a.max():.2f} dB (target {snr}, tolerance +-{TOLERANCE_DB})")
expected = sum(len(v) for v in raw_files.values())
for cond in CONDITIONS:
    if sum(1 for _ in (OUT / cond).glob("*/*.wav")) != expected:
        problems.append(f"{cond}: file count differs from {expected}")
print("problems:", problems or "none")
