"""Coach voice timing (docs/13 §9, decided 2026-11-02): hand-made event streams through the call-clock plan."""
from app.schedule import COACH_AFTER_TURN_S, plan

TURNS = [  # idx, speaker, offset_ms, duration_ms (natural schedule)
    {"idx": 1, "speaker": "A", "offset_ms": 0, "duration_ms": 4000},
    {"idx": 2, "speaker": "B", "offset_ms": 5200, "duration_ms": 5000},
    {"idx": 3, "speaker": "A", "offset_ms": 11400, "duration_ms": 3000},
    {"idx": 4, "speaker": "B", "offset_ms": 15600, "duration_ms": 3000},
]


def stream(card_lag_ms: int) -> list[dict]:
    """Agent turn 1 gets a spoken nudge whose card is shown `card_lag_ms` after the turn started."""
    ev = [
        ("session.started", {}, 0),
        ("turn.started", {"turn_idx": 1}, 0),
        ("finding.detected", {"turn_idx": 1, "id": "f1"}, card_lag_ms),
        ("coach.nudge", {"finding_id": "f1", "rule_id": "R3", "text": "Calm down."}, card_lag_ms),
        ("coach.speak", {"audio_url": "/audio/coach/R3_1.mp3", "duration_ms": 3000}, card_lag_ms),
        ("turn.ended", {"turn_idx": 1}, max(4000, card_lag_ms)),
        ("turn.started", {"turn_idx": 2}, 5200),
        ("turn.ended", {"turn_idx": 2}, 10200),
        ("turn.started", {"turn_idx": 3}, 11400),
        ("turn.ended", {"turn_idx": 3}, 14400),
        ("turn.started", {"turn_idx": 4}, 15600),
        ("turn.ended", {"turn_idx": 4}, 18600),
        ("session.ended", {}, 19000),
    ]
    return [{"seq": i, "type": t, "t_ms": ms, "data": d} for i, (t, d, ms) in enumerate(ev, 1)]


def one(p, kind):
    found = [e for e in p.events if e["type"] == kind]
    return found[0] if found else None


def test_flag_while_the_agent_is_still_speaking_voice_starts_half_a_second_after_the_turn_ends():
    p = plan(stream(card_lag_ms=2000), TURNS)
    end = p.starts[1] + 4000
    assert one(p, "coach.speak")["t_ms"] == end + round(COACH_AFTER_TURN_S * 1000)
    assert one(p, "coach.nudge")["t_ms"] < end  # the card was already there
    assert p.skipped == []


def test_flag_after_the_turn_ended_voice_plays_as_soon_as_the_card_is_shown():
    p = plan(stream(card_lag_ms=6000), TURNS)
    assert one(p, "coach.speak")["t_ms"] == one(p, "coach.nudge")["t_ms"] == p.starts[1] + 6000  # no wait, no extra delay
    assert p.skipped == []


def test_stale_voice_is_skipped_when_the_agents_next_turn_has_already_started_but_the_card_stays():
    p = plan(stream(card_lag_ms=14500), TURNS)
    assert one(p, "coach.speak") is None
    assert one(p, "coach.nudge") is not None
    assert p.skipped == [1] and p.agent_started_anyway == 1
    assert [e["seq"] for e in p.events] == list(range(1, len(p.events) + 1))  # the stream stays numbered without gaps

