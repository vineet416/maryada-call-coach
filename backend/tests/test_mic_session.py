"""Speak live end to end without keys: frames in, a fake speech recogniser, a stub language model, a fake clock.
A user-requested exception to "pure functions only" (docs/DECISIONS.md), limited to this file. The last test runs the real
live socket sender against a small local fake Prisma server (real sockets on localhost), like tests/test_stt_retry.py."""
import asyncio
import json
import time

import pytest
from app import db
from app.config import settings
from app.rules import llm
from app.rules.schemas import LlmOut
from app.security.credentials import Creds
from app.session import assets, mic, runner
from app.session.mic_rules import FrameLimiter
from app.stt.base import LiveAudio, SttError, SttGate, TranscriptSegment
from websockets.asyncio.server import serve

LOUD = b"\xb8\x0b\x48\xf4" * 256  # 64 ms
QUIET = bytes(1024)
SPEECH, PAUSE = [LOUD] * 16, [QUIET] * 21  # 1 s of speech, 1.34 s of quiet (a turn ends after 1.2 s)

R4_TEXT = "Aapke husband ne loan liya tha, EMI pending hai."
HELLO = "Namaste main Rohit Tarang Finserv se bol raha hoon, yeh call record ho rahi hai."


def _boom(message):
    def fail(*a, **k):
        raise AssertionError(message)
    return fail


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """No keys, no network, no database: anything that would touch them fails the test."""
    async def review(*a, **k):
        return LlmOut(), 5

    async def warm(*a, **k):
        return True
    monkeypatch.setattr(llm, "review", review)
    monkeypatch.setattr(llm, "warm_up", warm)
    monkeypatch.setattr(mic, "ist_hhmm", lambda: "11:00")  # the fake clock
    for fn in ("log_session_start", "log_turn", "log_finding", "log_session_end"):
        monkeypatch.setattr(db, fn, _boom("Speak live must not touch the database"))
    monkeypatch.setattr(assets, "reminder", lambda key: {"text": "Pick who answered.", "audio_url": "", "duration_ms": 0})
    monkeypatch.setattr(runner, "_switch_to_replay", _boom("no replay for mic sessions"))


def fake_stt(monkeypatch, texts, fail_from=None):
    """Replaces the speech recogniser: when a turn's audio is complete it returns the next scripted text."""
    async def segments(client, audio, profile, key, gate, label="", turn_started_at=None):
        n = int(label.split()[-1])
        while not audio.closed:
            await audio.wait_more()
        if fail_from is not None and n >= fail_from:
            raise SttError("scripted failure")
        yield TranscriptSegment(text=texts[min(n, len(texts)) - 1], lang="hi-IN", latency_ms=10, segment_idx=0,
                                audio_end_ms=audio.total_ms, is_last=True, stream_t0=turn_started_at or time.perf_counter())
    monkeypatch.setattr(mic, "_segments", segments)


async def start(clock=None):
    s = mic.new_mic_session(Creds("gk", "https://llm.example/v1", "lk", "m"), clock)
    s.mic.limiter = FrameLimiter(rate_x=1e6, burst_s=1e6)
    runner.start(s)
    return s


async def push(s, frames):
    for f in frames:
        mic.on_frame(s, f)
        await asyncio.sleep(0)


async def until(s, pred, timeout=10.0):
    end = time.monotonic() + timeout
    while not any(pred(e) for e in s.log.events):
        assert time.monotonic() < end, [e["type"] for e in s.log.events]
        await asyncio.sleep(0.02)


async def turns(s, n_turns):
    for n in range(1, n_turns + 1):
        await push(s, SPEECH + PAUSE)
        await until(s, lambda e, n=n: e["type"] == "turn.ended" and e["data"]["turn_idx"] == n)


async def end_call(s):
    mic.handle_control(s, {"type": "end"})
    await asyncio.wait_for(s.task, 20)


def of(s, type_):
    return [e["data"] for e in s.log.events if e["type"] == type_]


def run(coro, limit=40):
    return asyncio.run(asyncio.wait_for(coro, limit))


def test_call_with_clock_r4_after_selection_report_and_no_storage(monkeypatch):
    fake_stt(monkeypatch, [R4_TEXT, R4_TEXT])

    async def go():
        s = await start(clock="22:30")
        await turns(s, 1)  # nobody chosen yet, so R4 is not judged
        mic.handle_control(s, {"type": "set_answered_by", "value": "spouse"})
        mic.handle_control(s, {"type": "set_answered_by", "value": "nobody"})  # ignored
        await push(s, SPEECH + PAUSE)
        await until(s, lambda e: e["type"] == "turn.ended" and e["data"]["turn_idx"] == 2)
        await end_call(s)
        return s
    s = run(go())
    started = of(s, "session.started")[0]
    assert started["effective_mode"] == "mic" and started["simulated_start_time"] == "22:30"
    assert [d["answered_by"] for d in of(s, "context.updated")] == ["unknown", "spouse"]
    found = [(f["turn_idx"], f["rule_id"]) for f in of(s, "finding.detected")]
    assert (1, "R1") in found  # 22:30 is outside 08:00 to 19:00
    assert (1, "R4") not in found and (2, "R4") in found
    assert s.log.events[-1]["type"] == "session.ended" and not s.log.events[-1]["data"]["summary"]["stopped"]
    report = mic.build_session_report(s)
    assert report["source"] == "live" and report["scenario"]["call_time"] == "22:30" and len(report["turns"]) == 2
    assert any(f["rule_id"] == "R4" for f in report["findings"])
    assert s.private and s.creds is None  # keys wiped when the call ended


def test_default_clock_comes_from_the_live_ist_clock(monkeypatch):
    fake_stt(monkeypatch, [HELLO])

    async def go():
        s = await start()
        await turns(s, 1)
        await end_call(s)
        return s
    s = run(go())
    assert of(s, "session.started")[0]["simulated_start_time"] == "11:00"
    assert not [f for f in of(s, "finding.detected") if f["rule_id"] == "R1"]


def test_reminder_once_after_the_third_turn_while_unknown(monkeypatch):
    fake_stt(monkeypatch, [HELLO, "Aapki EMI baaki hai.", "Kab tak payment kar sakte hain?", "Theek hai."])

    async def go():
        s = await start()
        await turns(s, 4)
        await end_call(s)
        return s
    s = run(go())
    cards = [d for d in of(s, "coach.nudge") if d["rule_id"] == "SELECT"]
    assert len(cards) == 1 and cards[0]["audio_url"] == "" and not of(s, "coach.speak")  # clip missing: card only
    assert [d["answered_by"] for d in of(s, "context.updated")] == ["unknown"]


def test_no_reminder_when_chosen_before_the_third_turn(monkeypatch):
    fake_stt(monkeypatch, [HELLO, "Aapki EMI baaki hai.", "Kab tak payment kar sakte hain?"])

    async def go():
        s = await start()
        mic.handle_control(s, {"type": "set_answered_by", "value": "borrower"})
        await turns(s, 3)
        await end_call(s)
        return s
    assert not [d for d in of(run(go()), "coach.nudge") if d["rule_id"] == "SELECT"]


def test_reminder_voice_gates_the_microphone_and_barge_in_releases_it(monkeypatch):
    monkeypatch.setattr(assets, "reminder", lambda key: {"text": "Pick.", "audio_url": "/audio/coach/SELECT_1.mp3", "duration_ms": 4000})
    fake_stt(monkeypatch, [HELLO, "Aapki EMI baaki hai.", "Kab tak payment?"])

    async def go():
        s = await start()
        await turns(s, 3)
        await until(s, lambda e: e["type"] == "coach.speak", timeout=5)
        assert s.mic.coach_until > time.perf_counter()  # frames count as silence while the clip plays
        mic.handle_control(s, {"type": "barge_in"})
        assert s.mic.coach_until == 0.0
        await end_call(s)
        return s
    assert len(of(run(go()), "coach.speak")) == 1


def test_no_frames_ends_the_call_with_a_report(monkeypatch):
    monkeypatch.setattr(mic, "NO_FRAMES_S", 0.4)
    fake_stt(monkeypatch, [HELLO])

    async def go():
        s = await start()
        await asyncio.wait_for(s.task, 10)
        return s
    s = run(go(), 20)
    assert [b["kind"] for b in of(s, "banner")] == ["no_audio"] and s.log.events[-1]["type"] == "session.ended"


def test_time_limit_ends_gracefully_and_commits_the_open_turn(monkeypatch):
    monkeypatch.setattr(settings, "mic_session_max_s", 1.0)
    fake_stt(monkeypatch, [HELLO])

    async def go():
        s = await start()
        await push(s, SPEECH * 3)  # still speaking when the limit hits
        await asyncio.wait_for(s.task, 15)
        return s
    s = run(go(), 25)
    assert [b["kind"] for b in of(s, "banner")] == ["limit"]
    assert of(s, "transcript.final") and s.log.events[-1]["type"] == "session.ended"


def test_three_failed_turns_in_a_row_end_the_call_without_replay(monkeypatch):
    fake_stt(monkeypatch, ["x"], fail_from=1)

    async def go():
        s = await start()
        await turns(s, 3)
        await asyncio.wait_for(s.task, 15)
        return s
    s = run(go())
    assert [e["code"] for e in of(s, "error")] == ["stt_unavailable"]
    assert s.log.events[-1]["type"] == "session.ended" and not [b for b in of(s, "banner") if b["kind"] == "replay"]


def test_stop_cancels_and_a_finished_call_expires_from_memory(monkeypatch):
    fake_stt(monkeypatch, [HELLO])
    monkeypatch.setattr(settings, "mic_events_ttl_s", 0.2)

    async def go():
        s = await start()
        await push(s, SPEECH)
        runner.stop(s)
        await asyncio.wait_for(asyncio.gather(s.task, return_exceptions=True), 10)
        assert s.id in runner.SESSIONS
        await asyncio.sleep(0.5)
        return s
    s = run(go(), 20)
    assert s.log.events[-1]["data"]["summary"]["stopped"] and s.id not in runner.SESSIONS


def test_live_socket_sends_frames_as_they_come_then_commits(monkeypatch):
    """The real send_live path against a local fake Prisma server: audio fed in pieces, commit after close, a retry resends the buffer."""
    got = {"ms": 0, "commits": 0, "sockets": 0}

    async def handler(ws):
        got["sockets"] += 1
        first = got["sockets"] == 1
        await ws.send(json.dumps({"type": "connected"}))
        mine = 0
        async for m in ws:
            if isinstance(m, bytes):
                mine += len(m) // 16
                if first and mine >= 600:  # the first socket dies early
                    await ws.close(1011, "error")
                    return
            else:
                got["commits"] += 1
                got["ms"] = mine
                await ws.send(json.dumps({"type": "transcript", "is_final": True, "text": "hello", "audio_duration_ms": mine,
                                          "detected_language_code": "hi-IN", "latency": 20}))

    async def go():
        async with serve(handler, "127.0.0.1", 0) as server:
            monkeypatch.setattr(settings, "gnani_stt_ws_url", f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}")
            audio, segs = LiveAudio(), []

            async def feeder():
                for _ in range(30):  # 30 x 64 ms
                    audio.feed(LOUD)
                    await asyncio.sleep(0.03)
                audio.close()
            task = asyncio.create_task(feeder())
            async for seg in runner._segments(None, audio, {"model": "m", "language_code": "hi-IN"}, "k", SttGate(label="t"),
                                              label="turn 1", turn_started_at=time.perf_counter()):
                segs.append(seg)
            await task
            await asyncio.sleep(0.2)
            return segs
    segs = run(go(), 20)
    assert [s.text for s in segs] == ["hello"] and segs[0].via == "realtime_retry" and got["sockets"] == 2
    assert got["commits"] == 1 and got["ms"] >= 600  # the retry socket received the audio from the buffer
