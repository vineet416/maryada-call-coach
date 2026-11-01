"""Prisma realtime adapter: one WebSocket per turn, opened when the turn's audio starts, 1024-byte frames paced against an
absolute clock, finals only. Sockets are closed in the background so the next turn never waits for them."""
import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from pathlib import Path

import websockets

from ..config import settings
from .base import (
    BYTES_PER_MS,
    FRAME,
    FRAME_S,
    SttAuthError,
    SttError,
    SttGate,
    SttRefused,
    TranscriptSegment,
    is_last_segment,
    read_pcm,
)

log = logging.getLogger("maryada")

CATCHUP_X = 4.0  # a retried turn is sent at most this much faster than real time until it reaches the live position
COMMIT_TIMEOUT_S = 5.0  # after the commit, no message for this long ends the turn (REST is used if no text arrived)
POLL_S = 0.5  # the receive loop never waits longer than this without checking its exits
HARD_EXTRA_S = 10.0  # hard cap past the end of the turn's audio
CONNECT_S = 8.0
CLOSE_S = 3.0
_REFUSED_TEXT = re.compile(r"already|active|concurren|in use|too many|limit|busy", re.IGNORECASE)
_background: set[asyncio.Task] = set()  # keeps the closing tasks alive until they finish


async def paced_send(send: Callable[[bytes], Awaitable[None]], chunks: Iterable[bytes], frame_s: float,
                     clock: Callable[[], float] = time.monotonic,
                     sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                     deadline: Callable[[int], float] | None = None) -> None:
    """Send chunk n, then wait until start + (n + 1) * frame_s on the absolute clock (or `deadline(n)`). A late timer tick is
    made up by the next frame, so the total time stays the audio length (a sleep per frame drifts by the timer step on Windows)."""
    t0 = clock()
    for n, chunk in enumerate(chunks):
        await send(chunk)
        due = deadline(n) if deadline else t0 + (n + 1) * frame_s
        delay = due - clock()
        if delay > 0:
            await sleep(delay)


def catch_up_deadline(turn_start: float, begin: float, start_s: float, frame_s: float, pace: float,
                      speedup: float) -> Callable[[int], float]:
    """Send times for a retried turn that resumes at audio second `start_s` when the call is already further on: frame n goes out
    at the later of (a) `speedup` times faster than real time from `begin` and (b) the live position (turn_start + audio
    position x pace). So the stream catches up quickly and never gets ahead of the audio that has actually been played."""
    def due(n: int) -> float:
        live = turn_start + (start_s + (n + 1) * frame_s) * pace
        return max(live, begin + (n + 1) * frame_s * pace / speedup)
    return due


def _headers(profile: dict, api_key: str) -> dict:
    return {"x-api-key-id": api_key, "model": profile["model"], "language_code": profile["language_code"],
            "x-sample-rate": "8000"}


def _close_later(ws, gate: SttGate) -> None:
    """Close the socket in the background and give its slot back afterwards."""
    async def go() -> None:
        try:
            if ws is not None:
                await asyncio.wait_for(ws.close(), CLOSE_S)
        except Exception as e:  # noqa: BLE001 - a socket that will not close is dropped
            log.debug("stt socket close: %s", type(e).__name__)
        finally:
            await gate.release()
    task = asyncio.create_task(go())
    _background.add(task)
    task.add_done_callback(_background.discard)


def _error_for(msg: dict, crowded: bool) -> SttError:
    text = str(msg.get("message", ""))
    if crowded and _REFUSED_TEXT.search(text):
        return SttRefused(f"realtime error: {text[:80]}")
    return SttError(f"realtime error: {text[:80]}")


async def stream_turn(wav_path: Path, profile: dict, api_key: str, pace: float | None = None,
                      gate: SttGate | None = None, start_ms: int = 0, first_idx: int = 0, turn_started_at: float | None = None,
                      via: str = "realtime") -> AsyncIterator[TranscriptSegment]:
    """Yield each final segment as it arrives (not at the end of the turn). If Gnani refuses a second simultaneous socket
    the gate switches the call to serial mode and the turn is retried once, before any segment was delivered.
    A retry after a failed socket passes start_ms (resume after the delivered audio), first_idx (continue the segment numbers),
    turn_started_at (perf_counter when the turn's audio started: the stream then catches up at CATCHUP_X) and via="realtime_retry"."""
    gate = gate or SttGate()
    for attempt in range(2):
        delivered = 0
        try:
            async for seg in _stream_once(wav_path, profile, api_key, settings.pace if pace is None else pace, gate,
                                      start_ms, first_idx, turn_started_at, via):
                delivered += 1
                yield seg
            return
        except SttRefused as e:
            if delivered or attempt:
                raise SttError(str(e)) from None
            gate.go_serial(str(e))  # the retry waits for the other sockets to close


async def _stream_once(wav_path: Path, profile: dict, api_key: str, pace: float, gate: SttGate, start_ms: int, first_idx: int,
                       turn_started_at: float | None, via: str) -> AsyncIterator[TranscriptSegment]:
    pcm_all, total_ms = read_pcm(wav_path)
    pcm = pcm_all[start_ms * BYTES_PER_MS:]
    crowded = await gate.acquire() > 1  # another socket of this call is open: a refusal means "no second socket"
    ws = None
    sender: asyncio.Task | None = None
    try:
        try:
            ws = await websockets.connect(settings.gnani_stt_ws_url, additional_headers=_headers(profile, api_key),
                                          open_timeout=CONNECT_S)
            first = json.loads(await asyncio.wait_for(ws.recv(), CONNECT_S))  # "connected"
            if first.get("type") == "error":
                raise _error_for(first, crowded)
        except websockets.InvalidStatus as e:
            code = e.response.status_code
            if code in (401, 403):
                raise SttAuthError(f"realtime status {code}") from None
            raise (SttRefused if crowded and code in (409, 423, 429) else SttError)(f"realtime status {code}") from None

        committed_at: float | None = None

        async def send_all() -> None:
            nonlocal committed_at
            chunks = (pcm[i:i + FRAME] for i in range(0, len(pcm), FRAME))
            due = None
            if turn_started_at is not None:  # a retry: the call is already this far into the turn's audio
                begin = time.monotonic()
                due = catch_up_deadline(begin - (time.perf_counter() - turn_started_at), begin, start_ms / 1000, FRAME_S, pace, CATCHUP_X)
            await paced_send(ws.send, chunks, FRAME_S * pace, deadline=due)
            await ws.send(json.dumps({"type": "commit"}))
            committed_at = time.monotonic()

        t0 = turn_started_at if turn_started_at is not None else time.perf_counter()  # segment end = t0 + audio_end x pace
        started = time.monotonic()
        hard_end = started + (total_ms - start_ms) / 1000 * pace + COMMIT_TIMEOUT_S + HARD_EXTRA_S
        sender = asyncio.create_task(send_all())
        covered, idx, last_msg, saw_last = start_ms, 0, started, False
        while True:
            if saw_last and sender.done():
                return
            if sender.done() and not sender.cancelled() and sender.exception():
                raise sender.exception()  # type: ignore[misc]
            now = time.monotonic()
            if now > hard_end or (committed_at is not None and now - max(committed_at, last_msg) > COMMIT_TIMEOUT_S):
                log.warning("stt turn ended by timeout: committed=%s segments=%d", committed_at is not None, idx)
                return  # the caller uses REST when no text arrived
            try:
                m = json.loads(await asyncio.wait_for(ws.recv(), POLL_S))
            except TimeoutError:
                continue
            last_msg = time.monotonic()
            if m.get("type") == "error":
                raise _error_for(m, crowded and idx == 0)
            if m.get("type") != "transcript" or not m.get("is_final"):
                continue
            covered += int(m.get("audio_duration_ms", 0))
            saw_last = is_last_segment(covered, total_ms)
            held = time.monotonic()
            yield TranscriptSegment(text=m.get("text", "").strip(), lang=m.get("detected_language_code", ""),
                                    latency_ms=int(m.get("latency", 0)), segment_idx=first_idx + idx,
                                    audio_end_ms=covered, is_last=saw_last, stream_t0=t0, via=via)
            idx += 1
            resumed = time.monotonic()  # the consumer may have held us (it waits for the previous turn): that is not silence
            last_msg, hard_end = resumed, hard_end + (resumed - held)
    except SttError:
        raise
    except websockets.ConnectionClosed as e:
        code = e.rcvd.code if e.rcvd else None
        err = SttRefused if crowded and code in (1008, 4008, 4029) else SttError
        raise err(f"realtime closed {code}") from None
    except (websockets.WebSocketException, OSError, TimeoutError) as e:
        raise SttError(f"realtime {type(e).__name__}") from e
    finally:
        if sender is not None and not sender.done():
            sender.cancel()
        _close_later(ws, gate)  # the next turn does not wait for this


async def check_key(api_key: str) -> None:
    """Connection test: open the Prisma WebSocket with the key, wait for 'connected', close. No audio is sent.
    Raises SttAuthError when the key is refused, SttError for any other failure."""
    from .base import load_profile
    profile = load_profile("agent")
    hdr = {"x-api-key-id": api_key, "model": profile["model"], "language_code": profile["language_code"],
           "x-sample-rate": "8000"}
    try:
        async with websockets.connect(settings.gnani_stt_ws_url, additional_headers=hdr, open_timeout=CONNECT_S) as ws:
            await asyncio.wait_for(ws.recv(), CONNECT_S)
    except websockets.InvalidStatus as e:
        code = e.response.status_code
        raise (SttAuthError if code in (401, 403) else SttError)(f"status {code}") from None
    except websockets.ConnectionClosed as e:
        code = e.rcvd.code if e.rcvd else None
        raise (SttAuthError if code in (1008, 4001, 4003) else SttError)(f"closed {code}") from None
    except (websockets.WebSocketException, OSError, TimeoutError) as e:
        raise SttError(type(e).__name__) from None
