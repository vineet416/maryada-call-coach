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
