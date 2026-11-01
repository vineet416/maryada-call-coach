import asyncio
import math

import pytest
from app.stt.base import FRAME_S, SttError, SttGate, SttRefused
from app.stt.realtime import _error_for, paced_send

TICK = 0.0156  # Windows timer step: every sleep ends on the next tick


class FakeTime:
    def __init__(self) -> None:
        self.t = 0.0

    def clock(self) -> float:
        return self.t

    async def sleep(self, d: float) -> None:
        self.t += math.ceil(d / TICK) * TICK


def test_100_frames_take_the_audio_length_within_2_percent():
    ft = FakeTime()

    async def send(_chunk: bytes) -> None:
        pass
    asyncio.run(paced_send(send, [b"x"] * 100, FRAME_S, ft.clock, ft.sleep))
    audio_s = 100 * FRAME_S
    assert abs(ft.t - audio_s) / audio_s < 0.02


def test_a_sleep_per_frame_would_drift_past_2_percent():
    ft = FakeTime()

    async def naive() -> None:
        for _ in range(100):
            await ft.sleep(FRAME_S)
    asyncio.run(naive())
    assert (ft.t - 100 * FRAME_S) / (100 * FRAME_S) > 0.1  # the control: the fake timer really is coarse


def test_frames_are_sent_in_order_and_none_is_skipped():
    ft = FakeTime()
    got: list[bytes] = []

    async def send(chunk: bytes) -> None:
        got.append(chunk)
    chunks = [bytes([i]) for i in range(30)]
    asyncio.run(paced_send(send, chunks, FRAME_S, ft.clock, ft.sleep))
    assert got == chunks


def test_gate_allows_three_sockets_then_waits_and_serial_mode_allows_one():
    async def go() -> None:
        g = SttGate(max_sockets=3)
        assert [await g.acquire() for _ in range(3)] == [1, 2, 3]
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(g.acquire(), 0.05)  # a fourth waits for a release
        await g.release()
        assert await g.acquire() == 3
        g.go_serial("test")
        g.go_serial("test again")  # logged once, idempotent
        assert g.serial and g.refusals == 2
        for _ in range(3):
            await g.release()
        assert g.active == 0 and await g.acquire() == 1
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(g.acquire(), 0.05)  # serial: the second socket waits for the first
    asyncio.run(go())


def test_refusal_only_counts_when_another_socket_is_open_and_the_text_says_so():
    assert isinstance(_error_for({"message": "Session already active for this key"}, crowded=True), SttRefused)
    assert not isinstance(_error_for({"message": "Session already active for this key"}, crowded=False), SttRefused)
    flake = _error_for({"message": "A child process terminated abruptly, the process pool is not usable anymore"}, crowded=True)
    assert isinstance(flake, SttError) and not isinstance(flake, SttRefused)
