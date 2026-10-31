"""STT adapter contract. Prisma allows ONE active request per key, so every call goes through one lock."""
import asyncio
import io
import wave
from dataclasses import dataclass
from pathlib import Path

import yaml

from ..config import settings

FRAME = 1024  # bytes = 64 ms of 8 kHz PCM16 mono
BYTES_PER_MS = 16
LAST_SEGMENT_SLACK_MS = 400  # a segment ending this close to the audio end is the last one of the turn

_lock: asyncio.Lock | None = None


def gnani_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


class SttError(Exception):
    """Transport or protocol failure; the caller falls back (REST, then replay)."""


@dataclass
class TranscriptSegment:
    text: str
    lang: str
    latency_ms: int  # vendor-reported segment latency
    segment_idx: int
    audio_end_ms: int  # end of this segment within the turn audio (cumulative)
    is_last: bool
    stream_t0: float = 0.0  # perf_counter when the first audio frame left (segment end = t0 + audio_end_ms)


def load_profile(role: str) -> dict:
    prof = yaml.safe_load((settings.content_dir / "stt_profile.yaml").read_text(encoding="utf-8"))
    return {"model": prof["model"], "language_code": prof[role]["language_code"]}


def read_pcm(wav_path: Path) -> tuple[bytes, int]:
    """PCM16 mono 8 kHz frames and the duration in ms."""
    with wave.open(str(wav_path)) as w:
        pcm = w.readframes(w.getnframes())
    return pcm, len(pcm) // BYTES_PER_MS


def is_last_segment(audio_end_ms: int, total_ms: int) -> bool:
    return audio_end_ms >= total_ms - LAST_SEGMENT_SLACK_MS


def retry_start_ms(segments_done: int, covered_ms: int, rest_tried: bool) -> int | None:
    """Where the one REST retry of a turn starts (ms into the turn audio), or None = give up (caller falls back to replay).
    Nothing transcribed yet -> from the start; some segments done -> from where they ended (no duplicate text)."""
    if rest_tried:
        return None
    return 0 if segments_done == 0 else max(0, covered_ms)


def slice_wav(wav_path: Path, start_ms: int) -> bytes:
    """The WAV from start_ms to the end, as WAV bytes (start 0 = the file as is)."""
    with wave.open(str(wav_path)) as w:
        params = w.getparams()
        w.setpos(min(w.getnframes(), start_ms * w.getframerate() // 1000))
        frames = w.readframes(w.getnframes())
    out = io.BytesIO()
    with wave.open(out, "wb") as o:
        o.setparams(params)
        o.writeframes(frames)
    return out.getvalue()
