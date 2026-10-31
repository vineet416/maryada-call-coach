"""STT adapter contract. Prisma allows ONE active request per key, so every call goes through one lock."""
import asyncio
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
