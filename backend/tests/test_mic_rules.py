"""Speak live small rules: clock, frame validity and rate limit, reminder, answered-by values."""
from datetime import datetime

from app.session.mic_rules import (
    ANSWERED_BY,
    IST,
    FrameLimiter,
    ist_hhmm,
    reminder_due,
    valid_clock,
    valid_frame,
)


def test_clock_validator():
    assert [valid_clock(v) for v in ("00:00", "14:30", "23:59", "07:05")] == ["00:00", "14:30", "23:59", "07:05"]
    for bad in ("24:00", "7:05", "14:60", "14.30", "1430", "ab:cd", "", " 14:30", "14:30\n", None):
        assert valid_clock(bad) is None, bad


def test_ist_is_a_fixed_offset_of_five_and_a_half_hours():
    utc = datetime.fromisoformat("2026-11-02T13:05:00+00:00")
    assert ist_hhmm(utc) == "18:35"
    assert ist_hhmm(datetime(2026, 11, 2, 23, 40, tzinfo=IST)) == "23:40"


def test_frame_validity():
    assert valid_frame(1024) and valid_frame(2)
    assert not valid_frame(0) and not valid_frame(1023) and not valid_frame(1_000_000)


def test_rate_limit_allows_real_time_and_a_burst_but_not_a_flood():
    lim = FrameLimiter(rate_x=1.5, burst_s=3.0)
    t = 100.0
    ok = 0
    for _ in range(60):  # 60 frames of 64 ms (3.84 s) all at once: only the burst gets through
        ok += lim.allow(1024, t)
    assert 40 <= ok <= 50  # 3 s of burst = 46 frames
    lim = FrameLimiter(rate_x=1.5, burst_s=3.0)
    assert all(lim.allow(1024, 100.0 + i * 0.064) for i in range(500))  # real-time stream is never dropped


def test_rate_limit_recovers_after_a_pause():
    lim = FrameLimiter(rate_x=1.5, burst_s=3.0)
    for _ in range(100):
        lim.allow(1024, 0.0)
    assert not lim.allow(1024, 0.0)
    assert lim.allow(1024, 5.0)


def test_reminder_only_after_third_turn_while_unknown_and_once():
    assert not reminder_due(2, "unknown", False)
    assert reminder_due(3, "unknown", False)
    assert reminder_due(4, "unknown", False)
    assert not reminder_due(3, "unknown", True)
    for chosen in ANSWERED_BY:
        assert not reminder_due(5, chosen, False)


def test_selector_values():
    assert ANSWERED_BY == ("borrower", "spouse", "neighbour")
