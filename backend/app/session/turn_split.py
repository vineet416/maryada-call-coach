"""Speak live: cut the microphone stream (8 kHz PCM16) into agent turns. Pure: it only sees frames, so time is counted from the
audio itself and tests need no clock. A turn starts after START_MS of speech and ends after PAUSE_S of quiet or at MAX_TURN_S."""
import math
import struct
from collections import deque

BYTES_PER_MS = 16  # 8 kHz, 16-bit, mono

PAUSE_S = 1.2  # quiet this long ends a turn (tune here)
MAX_TURN_S = 25.0  # a turn this long is cut and the next one starts at once
START_MS = 200  # speech this long starts a turn
PREROLL_MS = 300  # audio kept from before the start, so the first word is not clipped
ABS_MIN_RMS = 300.0  # below this a frame is never speech
FLOOR_FACTOR = 3.0  # speech is louder than the noise floor times this
FLOOR_START, FLOOR_ALPHA = 60.0, 0.05  # the noise floor follows the quiet frames slowly

Out = tuple[str, object]  # ("start", None) | ("audio", bytes) | ("end", "pause" | "cap" | "finish")


def rms(pcm: bytes) -> float:
    n = len(pcm) // 2
    if n == 0:
        return 0.0
    return math.sqrt(sum(x * x for x in struct.unpack(f"<{n}h", pcm[:n * 2])) / n)


class TurnSplitter:
    def __init__(self, pause_s: float = PAUSE_S, max_turn_s: float = MAX_TURN_S) -> None:
        self.pause_ms, self.max_ms = pause_s * 1000, max_turn_s * 1000
        self.floor = FLOOR_START
        self.in_turn = False
        self._loud_ms = 0.0
        self._quiet_ms = 0.0
        self._turn_ms = 0.0
        self._pre: deque[tuple[bytes, float]] = deque()

    def feed(self, pcm: bytes) -> list[Out]:
        """One frame of any length in; the events it causes out (audio frames belong to the turn that is open)."""
        ms = len(pcm) / BYTES_PER_MS
        loud = rms(pcm) > max(ABS_MIN_RMS, self.floor * FLOOR_FACTOR)
        out: list[Out] = []
        if not self.in_turn:
            self._pre.append((pcm, ms))
            if loud:
                self._loud_ms += ms
            else:
                self._loud_ms = 0.0
                self._learn(pcm)
            while len(self._pre) > 1 and sum(m for _, m in self._pre) > PREROLL_MS + self._loud_ms:
                self._pre.popleft()
            if self._loud_ms >= START_MS:
                out.append(("start", None))
                out += [("audio", b) for b, _ in self._pre]
                self._turn_ms = sum(m for _, m in self._pre)
                self._pre.clear()
                self.in_turn, self._quiet_ms, self._loud_ms = True, 0.0, 0.0
            return out
        out.append(("audio", pcm))
        self._turn_ms += ms
        if loud:
            self._quiet_ms = 0.0
        else:
            self._quiet_ms += ms
            self._learn(pcm)
        if self._quiet_ms >= self.pause_ms:
            out.append(("end", "pause"))
            self.in_turn = False
            self._turn_ms = self._quiet_ms = 0.0
        elif self._turn_ms >= self.max_ms:
            out += [("end", "cap"), ("start", None)]
            self._turn_ms = self._quiet_ms = 0.0
        return out

    def finish(self) -> list[Out]:
        """The call is over: close a turn that is still open."""
        if not self.in_turn:
            return []
        self.in_turn = False
        return [("end", "finish")]

    def _learn(self, pcm: bytes) -> None:
        self.floor += FLOOR_ALPHA * (rms(pcm) - self.floor)
