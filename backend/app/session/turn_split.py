"""Speak live: cut the microphone stream (8 kHz PCM16) into agent turns. Pure: it only sees frames, so time is counted from the
audio itself and tests need no clock. A turn starts after START_MS of speech and ends after PAUSE_S of quiet or at MAX_TURN_S."""
import math
import statistics
import struct
from collections import deque

BYTES_PER_MS = 16  # 8 kHz, 16-bit, mono

PAUSE_S = 1.2  # quiet this long ends a turn (tune here)
MAX_TURN_S = 25.0  # a turn this long is cut and the next one starts at once
START_MS = 200  # speech this long starts a turn
PREROLL_MS = 300  # audio kept from before the start, so the first word is not clipped
ABS_MIN_RMS = 300.0  # below this a frame is never speech
FLOOR_FACTOR = 3.0  # speech is louder than the noise floor times this
FLOOR_START, FLOOR_ALPHA = 60.0, 0.05  # the noise floor starts here and follows the quiet frames of a turn slowly
FLOOR_CAP = 500.0  # a room or gain control that keeps the "quiet" up still gets a threshold (1500 RMS, about -27 dBFS) that speech can pass
RECENT_FRAMES = 48  # outside a turn the floor is the quietest tenth of the last 48 frames (about 3 s), loud-looking ones included
SPARSE_FRAMES = 12  # calibration: no turn starts in the first 12 frames (0.77 s); the audio of those frames still opens the first turn if it is speech
STEADY_RATIO = 1.6  # inside a turn, 48 frames whose loudest is less than this times the quietest and that sit under FLOOR_CAP are a hum, not speech

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
        self.last_turn: dict = {}  # the turn that ended last: speech_ms, longest_quiet_ms (the longest pause INSIDE it, for the log)
        self._loud_ms = 0.0
        self._loud_frames = 0
        self._seen = 0
        self._quiet_ms = 0.0
        self._turn_ms = 0.0
        self._longest_quiet_ms = 0.0
        self._pre: deque[tuple[bytes, float]] = deque()
        self._recent: deque[float] = deque(maxlen=RECENT_FRAMES)
        self._tail: deque[float] = deque(maxlen=RECENT_FRAMES)

    @property
    def threshold(self) -> float:
        return max(ABS_MIN_RMS, self.floor * FLOOR_FACTOR)

    def feed(self, pcm: bytes) -> list[Out]:
        """One frame of any length in; the events it causes out (audio frames belong to the turn that is open)."""
        ms = len(pcm) / BYTES_PER_MS
        level = rms(pcm)
        out: list[Out] = []
        if not self.in_turn:
            self._seen += 1
            self._learn_idle(level)  # first, so a steady hum above the old threshold is learned as the floor, not taken for speech
            self._pre.append((pcm, ms))
            if level > self.threshold:
                self._loud_ms += ms
                self._loud_frames += 1
            else:
                self._loud_ms, self._loud_frames = 0.0, 0
            while len(self._pre) > 1 and sum(m for _, m in self._pre) > PREROLL_MS + self._loud_ms:
                self._pre.popleft()
            if self._loud_ms >= START_MS and self._seen >= SPARSE_FRAMES:
                for _ in range(min(self._loud_frames, len(self._recent))):
                    self._recent.pop()  # these frames are the speech that starts the turn: they say nothing about the room
                self._set_floor()
                out.append(("start", None))
                out += [("audio", b) for b, _ in self._pre]
                self._begin_turn(sum(m for _, m in self._pre))
                self._pre.clear()
            return out
        out.append(("audio", pcm))
        self._turn_ms += ms
        self._tail.append(level)
        if level > self.threshold:
            self._longest_quiet_ms = max(self._longest_quiet_ms, self._quiet_ms)  # a pause inside the turn that speech ended
            self._quiet_ms = 0.0
            self._relearn_hum()
        else:
            self._quiet_ms += ms
            self.floor = min(FLOOR_CAP, self.floor + FLOOR_ALPHA * (level - self.floor))
        if self._quiet_ms >= self.pause_ms:
            out.append(("end", "pause"))
            self._close_turn()
        elif self._turn_ms >= self.max_ms:
            out += [("end", "cap"), ("start", None)]
            self._close_turn()
            self._begin_turn(0.0)  # the speaker is still going: the next turn starts at once
        return out

    def finish(self) -> list[Out]:
        """The call is over: close a turn that is still open."""
        if not self.in_turn:
            return []
        self._close_turn()
        return [("end", "finish")]

    def _begin_turn(self, turn_ms: float) -> None:
        self.in_turn = True
        self._turn_ms, self._quiet_ms, self._longest_quiet_ms = turn_ms, 0.0, 0.0
        self._loud_ms, self._loud_frames = 0.0, 0
        self._tail.clear()

    def _close_turn(self) -> None:
        self.last_turn = {"speech_ms": round(self._turn_ms - self._quiet_ms), "longest_quiet_ms": round(self._longest_quiet_ms)}
        self.in_turn = False
        self._recent.clear()
        self._recent.extend([self.floor] * SPARSE_FRAMES)  # the room as this turn learned it, not the window from before it
        self._turn_ms = self._quiet_ms = self._longest_quiet_ms = 0.0
        self._tail.clear()

    def _set_floor(self) -> None:
        vals = sorted(self._recent)
        if not vals:
            self.floor = FLOOR_START
        elif len(vals) < SPARSE_FRAMES:
            self.floor = min(vals[0], FLOOR_CAP)
        else:
            self.floor = min(FLOOR_CAP, vals[len(vals) // 10])

    def _learn_idle(self, level: float) -> None:
        self._recent.append(level)
        self._set_floor()

    def _relearn_hum(self) -> None:
        """Inside a turn, 3 s of frames that hardly vary and stay soft are a hum above the threshold: make it the floor,
        so the turn can end (speech varies a lot more than that from one frame to the next)."""
        if len(self._tail) < self._tail.maxlen or min(self._tail) <= 0:
            return
        if max(self._tail) < STEADY_RATIO * min(self._tail) and statistics.median(self._tail) <= FLOOR_CAP:
            self.floor = min(FLOOR_CAP, statistics.median(self._tail))
            self._tail.clear()
