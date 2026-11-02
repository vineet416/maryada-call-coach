"""Speak live: the small pure rules around a microphone call (frame limit, clock, answered-by values, the reminder)."""
import re
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))  # fixed offset: India has no daylight saving, and no tzdata package is needed
_CLOCK = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

ANSWERED_BY = ("borrower", "spouse", "neighbour")  # what the in-call selector may set (the start value is "unknown")
MAX_FRAME_BYTES = 16384  # a frame is about 64 ms (1024 bytes); anything much larger is not from our client
RATE_X = 1.5  # audio accepted per second of real time, at most
BURST_S = 3.0  # audio seconds that may arrive at once (a reconnect catching up)
REMINDER_AFTER_TURNS = 3  # the "choose who answered" voice reminder, once, at the end of this agent turn


def valid_clock(value: str | None) -> str | None:
    """`HH:MM` (00:00 to 23:59) or None."""
    return value if value is not None and _CLOCK.fullmatch(value) else None


def ist_hhmm(now: datetime | None = None) -> str:
    return (now or datetime.now(IST)).astimezone(IST).strftime("%H:%M")


def valid_frame(n_bytes: int) -> bool:
    return 0 < n_bytes <= MAX_FRAME_BYTES and n_bytes % 2 == 0


def reminder_due(agent_turns: int, answered_by: str, already_sent: bool) -> bool:
    """True once: the agent has finished their third turn and nobody has said who answered."""
    return agent_turns >= REMINDER_AFTER_TURNS and answered_by == "unknown" and not already_sent


class FrameLimiter:
    """Token bucket in seconds of audio: at most RATE_X seconds of audio per real second, with a BURST_S allowance."""

    def __init__(self, rate_x: float = RATE_X, burst_s: float = BURST_S) -> None:
        self.rate_x, self.burst_s = rate_x, burst_s
        self.tokens, self._at = burst_s, None

    def allow(self, n_bytes: int, now: float) -> bool:
        if self._at is not None:
            self.tokens = min(self.burst_s, self.tokens + (now - self._at) * self.rate_x)
        self._at = now
        cost = n_bytes / 16000  # 8 kHz x 2 bytes
        if self.tokens < cost:
            return False
        self.tokens -= cost
        return True
