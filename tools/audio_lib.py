"""Shared audio code for the notebooks and the evaluation harness (docs/11).

TTS client with cache, loudness, silence trim, phone chain, call assembly, earcon, STT helpers.
Keys come from the environment through backend settings and are never printed.
"""
import asyncio
import hashlib
import io
import json
import re
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path

import httpx2 as httpx
import numpy as np
import soundfile as sf
import yaml
from scipy import signal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools"))
import spike  # STT helpers and keyword recovery shared with the spike
from app.config import settings

CACHE = ROOT / "data" / "audio" / "_cache"
MODEL_TTS = "timbre-v3.0"
RUPEES_PER_CHAR = 0.0027
MAX_CHARS = 600
SENTENCE_GAP_MS = 120
MIN_REQUEST_INTERVAL_S = 1.0  # stays under 60 requests/min; the API also allows one active request only
_last_request = 0.0
requests_made = 0  # uncached TTS requests sent in this process


def mask(secret: str) -> str:
    return f"****{secret[-4:]}" if secret else "(not set)"


def load_yaml(rel: str) -> dict:
    return yaml.safe_load((ROOT / rel).read_text(encoding="utf-8"))


# ---------- TTS ----------
def split_text(text: str, limit: int = MAX_CHARS) -> list[str]:
    """Split at sentence boundaries into chunks of at most `limit` characters."""
    sentences = [s for s in re.split(r"(?<=[.!?।])\s+", text.strip()) if s]
    chunks, cur = [], ""
    for s in sentences:
        if cur and len(cur) + 1 + len(s) > limit:
            chunks.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        chunks.append(cur)
    return chunks or [text]


def credit_estimate(texts: list[str]) -> tuple[int, float]:
    chars = sum(len(t) for t in texts)
    return chars, round(chars * RUPEES_PER_CHAR, 2)


def _request_body(text: str, voice: str, language: str, speed: float, sample_rate: int) -> dict:
    return {"text": text, "voice": voice, "model": MODEL_TTS, "language": language, "speed": speed,
            "audio_config": {"encoding": "linear_pcm", "sample_rate": sample_rate, "container": "wav"}}


def cache_path(body: dict) -> Path:
    return CACHE / (hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest() + ".wav")


def uncached_requests(text: str, voice: str, language: str, speed: float, sample_rate: int) -> list[int]:
    """Character counts of the chunks of `text` that are not in the cache yet (one entry per TTS request needed)."""
    return [len(c) for c in split_text(text) if not cache_path(_request_body(c, voice, language, speed, sample_rate)).exists()]


def tts_chunk(body: dict, client: httpx.Client) -> bytes:
    """One TTS request through the cache. Retries 429/5xx with backoff, never 400/401/403."""
    global _last_request, requests_made
    CACHE.mkdir(parents=True, exist_ok=True)
    key = cache_path(body)
    if key.exists():
        return key.read_bytes()
    for attempt in range(5):
        wait = MIN_REQUEST_INTERVAL_S - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        r = client.post(settings.gnani_tts_url, headers={"x-api-key-id": settings.gnani_api_key_id}, json=body)
        _last_request = time.monotonic()
        if r.status_code == 200:
            requests_made += 1
            key.write_bytes(r.content)
            return r.content
        if r.status_code not in (429, 500, 502, 503, 504):
            raise RuntimeError(f"TTS {r.status_code} for voice {body['voice']}: {r.text[:200]}")
        time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"TTS gave {r.status_code} after retries: {r.text[:200]}")


def synthesize(text: str, voice: str, language: str, speed: float, sample_rate: int,
               client: httpx.Client) -> tuple[np.ndarray, int]:
    """Text of any length to a mono float32 array; chunks are joined with 120 ms gaps."""
    parts = []
    for chunk in split_text(text):
        data, sr = sf.read(io.BytesIO(tts_chunk(_request_body(chunk, voice, language, speed, sample_rate), client)),
                           dtype="float32")
        parts.append(data if data.ndim == 1 else data.mean(axis=1))
    gap = np.zeros(int(sr * SENTENCE_GAP_MS / 1000), dtype=np.float32)
    out = parts[0]
    for p in parts[1:]:
        out = np.concatenate([out, gap, p])
    return out, sr


def probe_sample_rates(client: httpx.Client, voice: str = "Prakash") -> dict:
    """Ask for each rate with a tiny text; report which the API honours (rate in the returned WAV)."""
    found = {}
    for rate in (48000, 44100, 24000, 22050, 16000, 8000):
        body = _request_body("Namaste.", voice, "hi-IN", 1.0, rate)
        r = client.post(settings.gnani_tts_url, headers={"x-api-key-id": settings.gnani_api_key_id}, json=body)
        if r.status_code == 200:
            found[rate] = sf.info(io.BytesIO(r.content)).samplerate
        else:
            found[rate] = f"{r.status_code} {r.text[:80]}"
        time.sleep(MIN_REQUEST_INTERVAL_S)
    return found


# ---------- loudness, trim, phone chain ----------
def _ffmpeg(args: list[str]) -> str:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", *args], capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr[-300:]}")
    return r.stderr


def loudnorm(x: np.ndarray, sr: int, target_lufs: float, true_peak: float = -1.5) -> np.ndarray:
    """Two-pass EBU R128 loudness normalisation with ffmpeg (linear gain, so no pumping), then a limiter
    0.5 dB below the true-peak ceiling so the finished file stays at or below `true_peak` dBTP."""
    with tempfile.TemporaryDirectory() as d:
        src, dst = Path(d, "in.wav"), Path(d, "out.wav")
        sf.write(src, x, sr, subtype="PCM_16")
        base = f"loudnorm=I={target_lufs}:TP={true_peak}:LRA=11"
        log = _ffmpeg(["-i", str(src), "-af", base + ":print_format=json", "-f", "null", "-"])
        m = json.loads(log[log.rindex("{"):log.rindex("}") + 1])
        af = (f"{base}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
              f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
        limit = 10 ** ((true_peak - 0.5) / 20)
        af += f",alimiter=limit={limit:.4f}:level=disabled"
        _ffmpeg(["-i", str(src), "-af", af, "-ar", str(sr), "-ac", "1", str(dst)])
        y, _ = sf.read(dst, dtype="float32")
    return _trim_to_target(y, sr, target_lufs, true_peak)


def _trim_to_target(y: np.ndarray, sr: int, target_lufs: float, true_peak: float) -> np.ndarray:
    """loudnorm and ebur128 can disagree by a few tenths of a LU on short clips; close the gap with one linear
    gain step, never letting the true peak rise above the ceiling."""
    m = measure_loudness(y, sr)
    gain = target_lufs - m["lufs"]
    if abs(gain) > 0.1 and np.isfinite(m["lufs"]):
        gain = min(gain, true_peak - m["true_peak"])
        y = (y * 10 ** (gain / 20)).astype(np.float32)
    return y


def measure_loudness(x: np.ndarray, sr: int) -> dict[str, float]:
    """Integrated loudness (LUFS), loudness range (LU) and true peak (dBTP) of a finished signal, via ffmpeg ebur128."""
    with tempfile.TemporaryDirectory() as d:
        src = Path(d, "in.wav")
        sf.write(src, x, sr, subtype="PCM_16")
        log = _ffmpeg(["-i", str(src), "-af", "ebur128=peak=true", "-f", "null", "-"])
    summary = log[log.rindex("Summary:"):]

    def grab(label: str) -> float:
        m = re.search(rf"{label}:\s+(-?[\d.]+|-inf)", summary)
        return float("-inf") if not m or m.group(1) == "-inf" else float(m.group(1))

    return {"lufs": grab("I"), "lra": grab("LRA"), "true_peak": grab("Peak")}


def measure_lufs(x: np.ndarray, sr: int) -> float:
    return measure_loudness(x, sr)["lufs"]


def phone_voice(x: np.ndarray, sr: int, target_lufs: float, cfg: dict | None = None) -> np.ndarray:
    """Call voice as heard: phone chain first, then the final loudness normalisation (the chain lowers the level)."""
    cfg = cfg or load_yaml("content/voices.yaml")["phone_chain"]
    return loudnorm(phone_chain(x, sr, cfg), cfg["resample_hz"], target_lufs)


def chime_at(lufs: float, sr: int) -> np.ndarray:
    """The earcon scaled so that it measures `lufs`. A chime is too short for a loudness reading, so eight of
    them back to back are measured and the same gain is applied to a single one."""
    c = earcon(sr)
    gain = 10 ** ((lufs - measure_lufs(np.tile(c, 8), sr)) / 20)
    return (c * gain).astype(np.float32)


def peak_dbfs(x: np.ndarray) -> float:
    p = float(np.max(np.abs(x))) if len(x) else 0.0
    return -120.0 if p == 0 else 20 * np.log10(p)


def trim_silence(x: np.ndarray, sr: int, keep_ms: int = 150, floor_db: float = -45.0) -> np.ndarray:
    """Cut leading and trailing silence, leaving at most `keep_ms` on each side."""
    frame = max(1, int(sr * 0.01))
    n = len(x) // frame
    if n == 0:
        return x
    rms = np.sqrt(np.mean(x[: n * frame].reshape(n, frame) ** 2, axis=1) + 1e-12)
    active = np.where(20 * np.log10(rms) > floor_db)[0]
    if len(active) == 0:
        return x
    keep = int(sr * keep_ms / 1000)
    start = max(0, active[0] * frame - keep)
    end = min(len(x), (active[-1] + 1) * frame + keep)
    return x[start:end]


def compressor(x: np.ndarray, sr: int, threshold_db: float, ratio: float, attack_ms: float, release_ms: float) -> np.ndarray:
    """Feed-forward peak compressor working on 1 ms frames."""
    frame = max(1, sr // 1000)
    n = int(np.ceil(len(x) / frame))
    padded = np.pad(x, (0, n * frame - len(x)))
    peak = np.abs(padded.reshape(n, frame)).max(axis=1) + 1e-9
    level_db = 20 * np.log10(peak)
    a_att, a_rel = np.exp(-1 / attack_ms), np.exp(-1 / release_ms)
    env = np.empty(n)
    cur = -120.0
    for i, v in enumerate(level_db):
        coef = a_att if v > cur else a_rel
        cur = coef * cur + (1 - coef) * v
        env[i] = cur
    gain_db = -np.maximum(env - threshold_db, 0) * (1 - 1 / ratio)
    gain = np.repeat(10 ** (gain_db / 20), frame)[: len(x)]
    return (x * gain).astype(np.float32)


def phone_chain(x: np.ndarray, sr: int, cfg: dict | None = None) -> np.ndarray:
    """Narrow-band call sound: 8 kHz, band-pass 300-3400 Hz (order 4), compressor (voices.yaml phone_chain)."""
    cfg = cfg or load_yaml("content/voices.yaml")["phone_chain"]
    target = cfg["resample_hz"]
    if sr != target:
        g = np.gcd(sr, target)
        x = signal.resample_poly(x, target // g, sr // g).astype(np.float32)
    lo, hi = cfg["bandpass_hz"]
    sos = signal.butter(4, [lo, hi], btype="bandpass", fs=target, output="sos")
    x = signal.sosfilt(sos, x).astype(np.float32)
    c = cfg["compressor"]
    return compressor(x, target, c["threshold_db"], c["ratio"], c["attack_ms"], c["release_ms"])


# ---------- files ----------
def write_wav(path: Path, x: np.ndarray, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, np.clip(x, -1.0, 1.0), sr, subtype="PCM_16")


def write_mp3(path: Path, x: np.ndarray, sr: int, kbps: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d, "in.wav")
        sf.write(tmp, np.clip(x, -1.0, 1.0), sr, subtype="PCM_16")
        _ffmpeg(["-i", str(tmp), "-ac", "1", "-codec:a", "libmp3lame", "-b:a", f"{kbps}k", str(path)])


def earcon(sr: int = 24000) -> np.ndarray:
    """Soft two-tone chime of 250 ms played right before the coach voice (docs/11 §10)."""
    t = np.arange(int(sr * 0.125)) / sr
    env = np.minimum(1, t / 0.01) * np.exp(-t * 14)
    def tone(f: float) -> np.ndarray:
        return np.sin(2 * np.pi * f * t) * env

    return (0.6 * np.concatenate([tone(880), tone(1320)])).astype(np.float32)


def assemble_call(turns: list[np.ndarray], sr: int, call_id: str, lead_ms: int = 300,
                  gap_ms: tuple[int, int] = (350, 700)) -> tuple[np.ndarray, list[int]]:
    """Join turns with random gaps (seed 42 + crc32 of the id) and return the audio plus each turn's start offset in ms."""
    rng = np.random.default_rng(42 + zlib.crc32(call_id.encode()))
    pos = int(sr * lead_ms / 1000)
    pieces, offsets = [np.zeros(pos, dtype=np.float32)], []
    for i, t in enumerate(turns):
        if i:
            gap = int(sr * rng.integers(gap_ms[0], gap_ms[1] + 1) / 1000)
            pieces.append(np.zeros(gap, dtype=np.float32))
            pos += gap
        offsets.append(round(pos * 1000 / sr))
        pieces.append(t)
        pos += len(t)
    return np.concatenate(pieces), offsets


# ---------- STT round trip ----------
def stt_roundtrip(wav_path: Path, combos: dict[str, dict]) -> dict[str, tuple[str, float, str]]:
    """Send one 8 kHz WAV through Prisma REST once per setting, one request at a time."""
    wav = wav_path.read_bytes()

    async def go() -> dict:
        out = {}
        async with httpx.AsyncClient(timeout=90) as client:
            for name, data in combos.items():
                out[name] = await spike.stt_rest(client, wav, data)
        return out

    return asyncio.run(go())


def stt_realtime(wav_path: Path, language_code: str, candidates: str | None = None) -> tuple[str, list[float], str]:
    return asyncio.run(spike.stt_realtime(wav_path.read_bytes(), language_code, candidates))


recovery = spike.recovery
key_terms = spike.key_terms


# ---------- audition clip rendering (shared by the audition notebooks) ----------
def target_lufs(voices_cfg: dict, group: str) -> float:
    return float(str(voices_cfg["loudness"][group]).split()[0])


def render_clip(j: dict, out: Path, voices_cfg: dict, client: httpx.Client, sample_rate: int = 48000) -> dict:
    """Load a clip from `out` when its files exist, otherwise synthesise it (cache first), normalise it and write
    `<clip>__<voice>__<var>__raw.wav` (and `__phone.wav` for call voices). Returns arrays and whether files were new."""
    stem = f"{j['clip']}__{j['voice']}__{j['var']}"
    raw_f, phone_f = out / f"{stem}__raw.wav", out / f"{stem}__phone.wav"
    is_call = j["group"] in ("agent", "borrower", "third_party")
    target = target_lufs(voices_cfg, j["group"])
    if raw_f.exists() and (phone_f.exists() or not is_call):
        x, sr = sf.read(raw_f, dtype="float32")
        p = sf.read(phone_f, dtype="float32")[0] if is_call else None
        new = False
    else:
        x, sr = synthesize(j["text"], j["voice"], j["lang"], j["speed"], sample_rate, client)
        x = loudnorm(trim_silence(x, sr), sr, target)
        write_wav(raw_f, x, sr)
        p = None
        if is_call:
            p = phone_voice(x, sr, target, voices_cfg["phone_chain"])
            write_wav(phone_f, p, 8000)
        new = True
    files = [(raw_f.name, "raw")] + ([(phone_f.name, "phone")] if is_call else [])
    return {"x": x, "sr": sr, "phone": p, "new": new, "files": files}
