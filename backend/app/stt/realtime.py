"""Prisma realtime adapter: one WebSocket per turn, 1024-byte frames at real-time cadence, finals only."""
import asyncio
import json
import time
from collections.abc import AsyncIterator
from pathlib import Path

import websockets

from ..config import settings
from .base import (
    BYTES_PER_MS,
    FRAME,
    SttError,
    TranscriptSegment,
    is_last_segment,
    read_pcm,
)

QUIET_S = 1.5  # after commit, no further segment for this long ends the turn
CONNECT_S = 8.0


async def stream_turn(wav_path: Path, profile: dict, api_key: str, pace: float | None = None) -> AsyncIterator[TranscriptSegment]:
    """Yield each final segment as it arrives (not at the end of the turn)."""
    pace = settings.pace if pace is None else pace
    pcm, total_ms = read_pcm(wav_path)
    hdr = {"x-api-key-id": api_key, "model": profile["model"], "language_code": profile["language_code"],
           "x-sample-rate": "8000"}
    try:
        async with websockets.connect(settings.gnani_stt_ws_url, additional_headers=hdr, open_timeout=CONNECT_S) as ws:
            await asyncio.wait_for(ws.recv(), CONNECT_S)  # "connected"

            async def send() -> None:
                for i in range(0, len(pcm), FRAME):
                    chunk = pcm[i:i + FRAME]
                    await ws.send(chunk)
                    await asyncio.sleep(len(chunk) / BYTES_PER_MS / 1000 * pace)
                await ws.send(json.dumps({"type": "commit"}))

            t0 = time.perf_counter()
            sender = asyncio.create_task(send())
            covered, idx = 0, 0
            try:
                while True:
                    wait = QUIET_S if sender.done() else None
                    try:
                        m = json.loads(await asyncio.wait_for(ws.recv(), wait))
                    except TimeoutError:
                        return
                    if m.get("type") != "transcript" or not m.get("is_final"):
                        continue
                    covered += int(m.get("audio_duration_ms", 0))
                    last = is_last_segment(covered, total_ms)
                    yield TranscriptSegment(text=m.get("text", "").strip(), lang=m.get("detected_language_code", ""),
                                            latency_ms=int(m.get("latency", 0)), segment_idx=idx,
                                            audio_end_ms=covered, is_last=last, stream_t0=t0)
                    idx += 1
                    if last and sender.done():
                        return
            finally:
                if not sender.done():
                    sender.cancel()
                if sender.done() and not sender.cancelled() and sender.exception():
                    raise sender.exception()  # type: ignore[misc]
    except (websockets.WebSocketException, OSError, TimeoutError) as e:
        raise SttError(f"realtime {type(e).__name__}") from e
