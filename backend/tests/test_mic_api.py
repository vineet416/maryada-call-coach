"""Speak live API: the sessions POST for mode "mic" (flag, keys, clock), the WebSocket carrying binary frames and control messages,
and the report endpoint. Handlers are called directly with a fake WebSocket; no network."""
import asyncio
import json
import time

import pytest
from app.api import rest
from app.config import settings
from app.rules import llm
from app.rules.schemas import LlmOut
from app.security.credentials import CredentialsIn
from app.session import mic, runner
from app.stt.base import TranscriptSegment
from fastapi import HTTPException

LOUD = b"\xb8\x0b\x48\xf4" * 256
QUIET = bytes(1024)
KEYS = CredentialsIn.model_validate({"gnani": {"api_key": "gk"}, "llm": {"base_url": "https://llm.example/v1", "api_key": "lk", "model": "m"}})


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    async def ok_url(url):
        return None

    async def review(*a, **k):
        return LlmOut(), 5

    async def warm(*a, **k):
        return True

    async def segments(client, audio, profile, key, gate, label="", turn_started_at=None):
        while not audio.closed:
            await audio.wait_more()
        yield TranscriptSegment(text="Namaste main Rohit Tarang Finserv se bol raha hoon", lang="hi-IN", latency_ms=1, segment_idx=0,
                                audio_end_ms=audio.total_ms, is_last=True, stream_t0=turn_started_at or time.perf_counter())
    monkeypatch.setattr(rest, "_checked_url", ok_url)
    monkeypatch.setattr(llm, "review", review)
    monkeypatch.setattr(llm, "warm_up", warm)
    monkeypatch.setattr(mic, "_segments", segments)
    monkeypatch.setattr(settings, "speak_live_enabled", True)


def post(**kw):
    return asyncio.run(rest.create_session(rest.StartBody(mode="mic", **kw)))


def code(excinfo):
    return excinfo.value.detail["error"]["code"]


def test_flag_off_refuses(monkeypatch):
    monkeypatch.setattr(settings, "speak_live_enabled", False)
    with pytest.raises(HTTPException) as e:
        post(credentials=KEYS)
    assert e.value.status_code == 403 and code(e) == "speak_live_off"


def test_keys_are_required(monkeypatch):
    monkeypatch.setattr(settings, "server_keys_enabled", False)
    with pytest.raises(HTTPException) as e:
        post()
    assert code(e) == "keys_required"


@pytest.mark.parametrize("bad", ["25:00", "9:30", "14:61", "noon"])
def test_bad_clock_is_refused(bad):
    async def go():
        with pytest.raises(HTTPException) as e:
            await rest.create_session(rest.StartBody(mode="mic", credentials=KEYS, clock=bad))
        assert code(e) == "bad_clock"
        assert not runner._live_active  # nothing was created
    asyncio.run(go())


def test_slots_busy_is_a_plain_503(monkeypatch):
    monkeypatch.setattr(settings, "max_live_sessions", 0)
    with pytest.raises(HTTPException) as e:
        post(credentials=KEYS)
    assert e.value.status_code == 503 and code(e) == "live_unavailable"


class FakeWS:
    def __init__(self, incoming):
        self.incoming, self.sent, self.closed = list(incoming), [], False

    async def accept(self):
        pass

    async def receive_json(self):
        return {"type": "start"}

    async def receive(self):
        while not self.incoming:
            await asyncio.sleep(0.05)
        item = self.incoming.pop(0)
        if item == "wait":
            await asyncio.sleep(0.6)
            return await self.receive()
        if item == "disconnect":
            return {"type": "websocket.disconnect", "code": 1001}
        if isinstance(item, bytes):
            return {"type": "websocket.receive", "bytes": item}
        return {"type": "websocket.receive", "text": item}

    async def send_json(self, env):
        self.sent.append(env)

    async def close(self, code=1000):
        self.closed = True


def test_websocket_takes_binary_frames_and_control_messages_and_the_report_follows():
    async def go():
        body = rest.StartBody(mode="mic", credentials=KEYS, clock="14:30")
        out = await rest.create_session(body)
        assert out["effective_mode"] == "mic" and out["ws_url"] == f"/ws/session/{out['session_id']}"
        s = runner.SESSIONS[out["session_id"]]
        s.mic.limiter.tokens = 1e6
        frames = [LOUD] * 16 + [QUIET] * 21
        ws = FakeWS([*frames, "not json", json.dumps({"type": "set_answered_by", "value": "neighbour"}), "wait",
                     json.dumps({"type": "end"})])
        await asyncio.wait_for(rest.ws_session(ws, s.id), 20)
        return s, ws
    s, ws = asyncio.run(asyncio.wait_for(go(), 30))
    types = [e["type"] for e in ws.sent]
    assert types[0] == "session.started" and types[-1] == "session.ended"
    assert "context.updated" in types and ws.sent[0]["data"]["simulated_start_time"] == "14:30"
    rep = rest.get_session_report(s.id)
    assert rep["source"] == "live" and rep["scenario"]["call_time"] == "14:30" and rep["turns"]


def test_report_is_404_until_the_call_is_over_and_for_other_sessions():
    async def go():
        out = await rest.create_session(rest.StartBody(mode="mic", credentials=KEYS))
        for sid in (out["session_id"], "nosuch"):
            with pytest.raises(HTTPException) as e:
                rest.get_session_report(sid)
            assert e.value.status_code == 404
        runner.SESSIONS[out["session_id"]].creds.wipe()
    asyncio.run(go())


def test_a_dropped_connection_does_not_end_the_call():
    """The browser reconnects with resume: the session keeps its state while no socket is attached."""
    async def go():
        out = await rest.create_session(rest.StartBody(mode="mic", credentials=KEYS))
        s = runner.SESSIONS[out["session_id"]]
        ws = FakeWS(["disconnect"])
        await asyncio.wait_for(rest.ws_session(ws, s.id), 10)
        assert not s.log.done  # still running on the server
        mic.handle_control(s, {"type": "end"})
        await asyncio.wait_for(s.task, 20)
        assert s.log.events[-1]["type"] == "session.ended"
    asyncio.run(asyncio.wait_for(go(), 40))
