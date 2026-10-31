"""Prisma REST adapter (fallback): one POST per turn, one segment back."""
import time
from pathlib import Path

import httpx2 as httpx

from ..config import settings
from .base import SttError, TranscriptSegment


async def transcribe_turn(client: httpx.AsyncClient, wav_path: Path, profile: dict, api_key: str) -> list[TranscriptSegment]:
    t0 = time.perf_counter()
    try:
        r = await client.post(settings.gnani_stt_rest_url, headers={"X-API-Key-ID": api_key},
                              files={"audio_file": ("turn.wav", wav_path.read_bytes(), "audio/wav")},
                              data={"model": profile["model"], "language_code": profile["language_code"]})
    except httpx.HTTPError as e:
        raise SttError(f"rest {type(e).__name__}") from e
    if r.status_code != 200:
        raise SttError(f"rest status {r.status_code}")
    j = r.json()
    return [TranscriptSegment(text=j.get("transcript", "").strip(), lang=j.get("detected_language_code", ""),
                              latency_ms=int((time.perf_counter() - t0) * 1000), segment_idx=0,
                              audio_end_ms=0, is_last=True, stream_t0=time.perf_counter())]
