import asyncio

from app import db, replay
from app.config import settings
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


def test_daily_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "t.db")
    db.init_db()
    assert [db.try_take_slot(2) for _ in range(3)] == [True, True, False]


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
