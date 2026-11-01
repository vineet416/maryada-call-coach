import asyncio

from app import replay
from app.schedule import plan as clock_plan
from app.session.events import EventLog
from app.stt.base import is_last_segment


def test_last_segment_slack():
    assert is_last_segment(9700, 10000)
    assert not is_last_segment(8000, 10000)


def test_event_log_seq_and_resume():
    log = EventLog()
    for t in ("a", "b", "c"):
        log.emit(t, {})
    log.close()

    async def collect(last):
        return [e["seq"] async for e in log.follow(last)]

    assert asyncio.run(collect(0)) == [1, 2, 3]
    assert asyncio.run(collect(2)) == [3]


def test_replay_schedule_and_labels():
    evs = [{"seq": 1, "type": "session.started", "t_ms": 0, "data": {"effective_mode": "live"}},
           {"seq": 2, "type": "transcript.final", "t_ms": 1500, "data": {"source": "live"}},
           {"seq": 3, "type": "turn.ended", "t_ms": 1700, "data": {}}]
    rep = replay.as_replay(evs)
    assert rep[0]["data"]["effective_mode"] == "replay" and rep[1]["data"]["source"] == "replay"
    assert evs[0]["data"]["effective_mode"] == "live"  # the recording is untouched
    assert [round(d, 1) for d, _ in replay.schedule(rep)] == [0.0, 1.5, 0.2]
    assert [e["seq"] for e in rep] == [1, 2, 3] and [e["t_ms"] for e in rep] == [0, 1500, 1700]


def test_remaining_rebases_time():
    evs = [{"seq": 1, "type": "session.started", "t_ms": 0, "data": {}},
           {"seq": 2, "type": "turn.started", "t_ms": 100, "data": {"turn_idx": 1}},
           {"seq": 3, "type": "turn.ended", "t_ms": 900, "data": {"turn_idx": 1}},
           {"seq": 4, "type": "turn.started", "t_ms": 1500, "data": {"turn_idx": 2}},
           {"seq": 5, "type": "session.ended", "t_ms": 2500, "data": {}}]
    rest = replay.remaining(evs, 1)
    assert [e["seq"] for e in rest] == [4, 5] and [e["t_ms"] for e in rest] == [0, 1000]
    assert replay.remaining(evs, 2) == []


def test_tokens_continue_across_segments():
    from app.session.runner import tokens_for
    a = tokens_for(0, "Madam ye sab")
    b = tokens_for(len(a), "मेरे को आज")
    assert [t["i"] for t in a + b] == [0, 1, 2, 3, 4, 5]
    assert a[0]["lang"] == "en" and b[0]["lang"] == "hi"


def test_rest_retry_decision():
    from app.stt.base import retry_start_ms
    assert retry_start_ms(0, 0, rest_tried=False) == 0  # failed before any segment: whole turn over REST
    assert retry_start_ms(2, 6400, rest_tried=False) == 6400  # failed mid-turn: continue after what was delivered
    assert retry_start_ms(2, 6400, rest_tried=True) is None  # REST already tried once: give up (replay)
    assert retry_start_ms(0, 0, rest_tried=True) is None


def test_slice_wav(tmp_path):
    import wave

    from app.stt.base import slice_wav
    p = tmp_path / "t.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x01\x00" * 8000)  # 1 s
    import io
    with wave.open(io.BytesIO(slice_wav(p, 250))) as w:
        assert w.getnframes() == 6000 and w.getframerate() == 8000
    with wave.open(io.BytesIO(slice_wav(p, 5000))) as w:
        assert w.getnframes() == 0


TURNS = [{"idx": 1, "speaker": "A", "offset_ms": 300, "duration_ms": 2000},
         {"idx": 2, "speaker": "B", "offset_ms": 3500, "duration_ms": 8000},
         {"idx": 3, "speaker": "A", "offset_ms": 13000, "duration_ms": 2000},
         {"idx": 4, "speaker": "B", "offset_ms": 16000, "duration_ms": 2000}]


def _recorded(nudge_lag=2500, with_nudge=True):
    ev = lambda seq, typ, t, **d: {"seq": seq, "type": typ, "t_ms": t, "data": d}
    nudge = [ev(3, "coach.nudge", 100 + nudge_lag, rule_id="R3")] if with_nudge else []
    speak = [ev(5, "coach.speak", 3300, duration_ms=4000)] if with_nudge else []
    return [ev(1, "session.started", 20), ev(2, "turn.started", 100, turn_idx=1), *nudge,
            ev(4, "turn.ended", 3100, turn_idx=1), *speak,
            ev(6, "turn.started", 9000, turn_idx=2), ev(7, "transcript.final", 9500, turn_idx=2),
            ev(8, "turn.ended", 12000, turn_idx=2), ev(9, "turn.started", 14000, turn_idx=3),
            ev(10, "turn.started", 18000, turn_idx=4)]


def _times(out):
    return {(e["type"], e["data"].get("turn_idx")): e["t_ms"] for e in out}


def test_coach_plays_under_the_next_speaker_and_the_agent_follows_it():
    out = replay.retime(_recorded(), TURNS)
    t = _times(out)
    assert t[("coach.speak", None)] == 3500 + 3500  # 3.5 s after the borrower's turn starts
    # clip ends at 11000; the agent follows 1.0 s later (12000) but not before the borrower's turn plus the minimum gap
    assert t[("turn.started", 3)] == 12400
    assert t[("turn.started", 4)] == 16000 - 600  # later turns keep their natural spacing from the agent
    assert t[("transcript.final", 2)] == 3500 + 500  # events keep their lag after their own turn
    assert [e["seq"] for e in out] == list(range(1, len(out) + 1))


def test_agent_waits_two_seconds_for_a_nudge_that_is_not_ready_then_starts():
    plan = clock_plan(_recorded(nudge_lag=30000), TURNS)
    t = _times(plan.events)
    assert plan.agent_started_anyway == 1
    assert t[("turn.started", 3)] == 13000 + 2000
    assert t[("coach.speak", None)] == 300 + 30000  # plays when ready


def test_no_nudge_keeps_the_natural_gaps():
    t = _times(replay.retime(_recorded(with_nudge=False), TURNS))
    assert [t[("turn.started", i)] for i in (1, 2, 3, 4)] == [300, 3500, 13000, 16000]


def test_nudge_on_the_last_agent_turn_plays_after_it_ends():
    turns = TURNS[:1]
    evs = [e for e in _recorded() if e["data"].get("turn_idx") in (1, None)]
    t = _times(replay.retime(evs, turns))
    assert t[("coach.speak", None)] == 300 + 2000 + 1000


def test_pause_option_moves_what_happens_after_the_clip():
    out = replay.retime(_recorded(), TURNS, hold=True)
    t = _times(out)
    assert t[("coach.speak", None)] == 7000 and t[("turn.started", 2)] == 3500  # started before the clip: untouched
    assert t[("turn.started", 3)] == 13000 + 4000 + 300  # natural start plus the clip and the pause gap


def test_two_nudges_close_together_never_overlap():
    turns = [{"idx": i, "speaker": "A" if i % 2 else "B", "offset_ms": 300 + (i - 1) * 4000, "duration_ms": 3000} for i in range(1, 7)]
    ev = lambda seq, typ, t, **d: {"seq": seq, "type": typ, "t_ms": t, "data": d}
    evs = [ev(1, "turn.started", 100, turn_idx=1), ev(2, "coach.nudge", 600, turn_idx=1), ev(3, "turn.ended", 900, turn_idx=1),
           ev(4, "coach.speak", 950, duration_ms=3500),
           ev(5, "turn.started", 4100, turn_idx=2), ev(6, "turn.started", 8100, turn_idx=3), ev(7, "coach.nudge", 8400, turn_idx=3),
           ev(8, "coach.speak", 9000, duration_ms=3500), ev(9, "turn.started", 12100, turn_idx=4)]
    plan = clock_plan(evs, turns)
    first, second = plan.coach[1], plan.coach[3]
    assert second >= first + 3500 + 1000  # at least 1.0 s between two clips
