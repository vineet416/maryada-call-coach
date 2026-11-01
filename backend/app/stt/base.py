"""STT adapter contract. Each turn opens its own Prisma socket when its audio starts (see SttGate for the per-call limit)."""
import asyncio
import hashlib
import io
import logging
import wave
from dataclasses import dataclass
from pathlib import Path

import yaml

from ..config import settings

log = logging.getLogger("maryada")

FRAME = 1024  # bytes = 64 ms of 8 kHz PCM16 mono
BYTES_PER_MS = 16
FRAME_S = FRAME / BYTES_PER_MS / 1000
LAST_SEGMENT_SLACK_MS = 400  # a segment ending this close to the audio end is the last one of the turn
MAX_SOCKETS = 3  # simultaneous Prisma sockets per call
SLOT_WAIT_S = 20.0  # longest wait for a free socket slot


_rest_locks: dict[str, asyncio.Lock] = {}  # Prisma REST allows one request per key (429 otherwise): one REST call at a time per key


def rest_lock(key: str) -> asyncio.Lock:
    d = hashlib.sha256(key.encode()).hexdigest()[:16]  # the key itself is never stored
    if len(_rest_locks) > 64:
        for k in [k for k, v in _rest_locks.items() if not v.locked() and k != d]:
            del _rest_locks[k]
    return _rest_locks.setdefault(d, asyncio.Lock())


class SttError(Exception):
    """Transport or protocol failure; the caller falls back (REST, then replay)."""


class SttAuthError(SttError):
    """Gnani refused the key (401/403). Not retried and never replaced by another key."""


class SttRefused(SttError):
    """Gnani refused an additional simultaneous socket (observed, not documented: 429/4xx, an 'already active' style error)."""


class SttGate:
    """Per-call limit on simultaneous sockets. Parallel mode (default): up to MAX_SOCKETS at once, so a turn never waits for the
    previous turn's close. If Gnani refuses a second socket, the call drops to serial mode (one socket at a time) for good."""

    def __init__(self, label: str = "", max_sockets: int = MAX_SOCKETS) -> None:
        self.label, self.max_sockets = label, max_sockets
        self.serial, self.active, self.refusals = False, 0, 0
        self._cv = asyncio.Condition()

    async def acquire(self) -> int:
        """Wait for a free slot (bounded). Returns how many sockets are open including this one."""
        async def _wait() -> int:
            async with self._cv:
                await self._cv.wait_for(lambda: self.active < (1 if self.serial else self.max_sockets))
                self.active += 1
                return self.active
        try:
            return await asyncio.wait_for(_wait(), SLOT_WAIT_S)
        except TimeoutError:
            raise SttError("no free socket slot") from None

    async def release(self) -> None:
        async with self._cv:
            self.active = max(0, self.active - 1)
            self._cv.notify_all()

    def go_serial(self, why: str) -> None:
        self.refusals += 1
        if not self.serial:
            self.serial = True
            log.warning("session=%r a second Gnani socket was refused (%s): serial mode for the rest of this call",
                        self.label, why)


@dataclass
class TranscriptSegment:
    text: str
    lang: str
    latency_ms: int  # vendor-reported segment latency
    segment_idx: int
    audio_end_ms: int  # end of this segment within the turn audio (cumulative)
    is_last: bool
    stream_t0: float = 0.0  # perf_counter when the first audio frame left (segment end = t0 + audio_end_ms)
    via: str = "realtime"  # "rest" for a segment from the REST fallback (it covers audio that may not have been played yet)


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
