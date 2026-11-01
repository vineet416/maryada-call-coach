"""One retry on a new realtime socket before REST. Uses a small local fake Prisma server (real sockets on localhost, no Gnani)."""
import asyncio
import itertools
import json
import time
import wave

import pytest
from app.config import settings
from app.session import runner
from app.stt import realtime
from app.stt.base import SttGate, TranscriptSegment
from websockets.asyncio.server import serve

PACE = 0.2  # fast tests: a 3 s turn plays in 0.6 s
PROFILE = {"model": "m", "language_code": "hi-IN"}


@pytest.fixture
def wav(tmp_path):
    p = tmp_path / "t.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 8000 * 3)  # 3 s
    return p


def final(ms):
    return json.dumps({"type": "transcript", "is_final": True, "text": f"text {ms}", "audio_duration_ms": ms,
                       "detected_language_code": "hi-IN", "latency": 50})


def make_handler(plan):
    state = {"n": 0, "recv_ms": []}

    async def handler(ws):
        i = state["n"]
        state["n"] += 1
        state["recv_ms"].append(0)
        mode = plan[min(i, len(plan) - 1)]
        await ws.send(json.dumps({"type": "connected"}))
        got, sent_first = 0, False
        async for m in ws:
            if isinstance(m, bytes):
                got += len(m) // 16
                state["recv_ms"][i] = got
                if mode == "close_early" and got >= 500:
                    await ws.send(json.dumps({"type": "error", "message": "A child process terminated abruptly, the process pool is not usable anymore"}))
                    await ws.close(1011, "error")
                    return
                if mode == "partial_then_close":
                    if got >= 800 and not sent_first:
                        sent_first = True
                        await ws.send(final(800))
                    if got >= 1000:
                        await ws.close(1011, "error")
                        return
            elif mode != "silent":  # the commit message
                await ws.send(final(got))
    return handler, state


def run_turn(monkeypatch, wav, plan, rest_calls=None):
    monkeypatch.setattr(settings, "pace", PACE)
    monkeypatch.setattr(realtime, "POLL_S", 0.05)
    monkeypatch.setattr(realtime, "COMMIT_TIMEOUT_S", 0.4)

    async def fake_rest(client, wav_path, profile, key, start_ms=0, first_idx=0):
        if rest_calls is not None:
            rest_calls.append(start_ms)
        return [TranscriptSegment(text="rest text", lang="hi-IN", latency_ms=1, segment_idx=first_idx, audio_end_ms=0,
                                  is_last=True, stream_t0=time.perf_counter(), via="rest")]
    monkeypatch.setattr(runner.stt_rest, "transcribe_turn", fake_rest)
    handler, state = make_handler(plan)
    out = {"segs": [], "t": []}

    async def go():
        async with serve(handler, "127.0.0.1", 0) as server:
            monkeypatch.setattr(settings, "gnani_stt_ws_url", f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}")
            gate = SttGate(label="test")
            t0 = time.perf_counter()
            async for seg in runner._segments(None, wav, PROFILE, "k", gate, label="turn 1", turn_started_at=t0):
                out["segs"].append(seg)
                out["t"].append(time.perf_counter() - t0)
            await asyncio.sleep(0.3)  # let the background closes finish
            out["gate"] = gate
    asyncio.run(asyncio.wait_for(go(), 30))
    out["state"] = state
    return out


def test_normal_turn_is_unchanged(monkeypatch, wav):
    o = run_turn(monkeypatch, wav, ["ok"])
    assert [s.via for s in o["segs"]] == ["realtime"] and o["state"]["n"] == 1
    assert o["gate"].stats() == {"early_closes": 0, "retries": 0, "retry_ok": 0, "rest_turns": 0}


def test_early_close_then_retry_succeeds_and_the_turn_stays_live(monkeypatch, wav):
    rest = []
    o = run_turn(monkeypatch, wav, ["close_early", "ok"], rest)
    assert [s.via for s in o["segs"]] == ["realtime_retry"] and o["segs"][0].is_last
    assert o["state"]["n"] == 2 and rest == []  # a second socket, and REST was not needed
    assert o["gate"].stats() == {"early_closes": 1, "retries": 1, "retry_ok": 1, "rest_turns": 0}
    assert o["state"]["recv_ms"][1] >= 2900  # the retry resent the turn's audio from its start


def test_retry_text_is_never_shown_before_its_audio_has_ended(monkeypatch, wav):
    o = run_turn(monkeypatch, wav, ["close_early", "ok"])
    assert o["segs"] and all(s.via == "realtime_retry" for s in o["segs"])
    for seg, t in zip(o["segs"], o["t"], strict=True):
        assert t >= seg.audio_end_ms / 1000 * PACE - 0.02  # the catch-up never gets ahead of the live position
    assert runner.rest_hold_s(10.0, 3000, 10.1, PACE) == pytest.approx(0.5)  # and the runner's hold covers what is left


def test_retry_that_fails_too_falls_back_to_rest_once(monkeypatch, wav):
    rest = []
    o = run_turn(monkeypatch, wav, ["close_early", "close_early"], rest)
    assert [s.via for s in o["segs"]] == ["rest"] and rest == [0]
    assert o["state"]["n"] == 2  # one retry, not more
    assert o["gate"].stats() == {"early_closes": 1, "retries": 1, "retry_ok": 0, "rest_turns": 1}


def test_a_silent_socket_after_the_commit_is_retried(monkeypatch, wav):
    o = run_turn(monkeypatch, wav, ["silent", "ok"])
    assert [s.via for s in o["segs"]] == ["realtime_retry"] and o["gate"].stats()["rest_turns"] == 0


def test_text_that_arrived_is_kept_and_only_the_rest_is_retried(monkeypatch, wav):
    rest = []
    o = run_turn(monkeypatch, wav, ["partial_then_close", "ok"], rest)
    assert [s.via for s in o["segs"]] == ["realtime", "realtime_retry"] and rest == []
    assert [s.segment_idx for s in o["segs"]] == [0, 1]  # numbering continues
    assert o["segs"][0].audio_end_ms == 800 and o["segs"][1].audio_end_ms == 3000  # absolute audio positions
    assert 2100 <= o["state"]["recv_ms"][1] <= 2300  # the retry sent only the audio after the delivered text


def test_catch_up_is_at_most_4x_and_never_ahead_of_the_live_position():
    ts, begin, frame = 100.0, 103.0, 0.064  # the turn's audio started 3 s before the retry begins
    due = realtime.catch_up_deadline(ts, begin, 0.0, frame, 1.0, 4.0)
    n = int(10.0 / frame)
    times = [due(i) for i in range(n)]
    assert all(t >= ts + (i + 1) * frame - 1e-9 for i, t in enumerate(times))  # not ahead of the audio that has played
    assert all(b - a <= frame + 1e-9 for a, b in itertools.pairwise(times))
    assert times[3] - times[2] == pytest.approx(frame / 4)  # catching up at 4x
    assert times[-1] == pytest.approx(ts + n * frame)  # finishes with the live audio
    caught = next(i for i, t in enumerate(times) if t <= ts + (i + 1) * frame + 1e-9)
    assert caught * frame == pytest.approx(4.0, abs=0.2)  # 3 s behind, gaining 0.75 s per second: live again after 4 s of audio


def test_rest_starts_after_the_text_that_was_delivered_when_the_retry_fails_too(monkeypatch, wav):
    rest = []
    o = run_turn(monkeypatch, wav, ["partial_then_close", "close_early"], rest)
    assert [s.via for s in o["segs"]] == ["realtime", "rest"] and rest == [800]  # REST covers only what is left
    assert o["gate"].stats() == {"early_closes": 1, "retries": 1, "retry_ok": 0, "rest_turns": 1}


def test_a_rejected_key_is_never_retried(monkeypatch, wav):
    from app.stt.base import SttAuthError
    monkeypatch.setattr(settings, "pace", PACE)
    calls = {"n": 0}

    def reject(conn, request):
        calls["n"] += 1
        return conn.respond(401, "no\n")

    async def go():
        async with serve(lambda ws: None, "127.0.0.1", 0, process_request=reject) as server:
            monkeypatch.setattr(settings, "gnani_stt_ws_url", f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}")
            gate = SttGate(label="test")
            with pytest.raises(SttAuthError):
                async for _ in runner._segments(None, wav, PROFILE, "k", gate, label="turn 1", turn_started_at=time.perf_counter()):
                    pass
            return gate
    gate = asyncio.run(asyncio.wait_for(go(), 15))
    assert calls["n"] == 1 and gate.stats() == {"early_closes": 0, "retries": 0, "retry_ok": 0, "rest_turns": 0}
