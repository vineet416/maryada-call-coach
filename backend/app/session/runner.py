"""Session runner: one asyncio task per session; live (Prisma + engine) or replay. Event order: docs/02 §2 as changed by docs/13."""
import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime

import httpx2 as httpx

from .. import db, replay
from ..config import settings
from ..rules import llm, risk
from ..rules.engine import deep_findings, fast_findings
from ..rules.schemas import Finding, Turn
from ..rules.text import tokenize
from ..stt import realtime
from ..stt import rest as stt_rest
from ..stt.base import (
    SttError,
    TranscriptSegment,
    gnani_lock,
    load_profile,
    retry_start_ms,
)
from . import assets
from .events import EventLog

log = logging.getLogger("maryada.session")

FIRST_ANSWER_S = 4.0  # docs/13 §4.5: wait this long for the LLM before closing a turn; later answers are "late" updates
FIRST_SEGMENT_S = 15.0  # docs/01 §4: no transcript for this long -> fallback
COACH_GAP_MS = 300
MAX_SPOKEN_PER_CALL = 3
_RANK = {"good_practice": 0, "advisory": 1, "needs_review": 2, "violation": 3}

SESSIONS: dict[str, "Session"] = {}
_live_active: str | None = None


class Session:
    def __init__(self, scenario_id: str, mode: str, reason: str | None = None) -> None:
        self.id = uuid.uuid4().hex[:10]
        self.scenario_id, self.effective_mode, self.reason = scenario_id, mode, reason
        self.log = EventLog()
        self.task: asyncio.Task | None = None
        self.api_key: str | None = None  # BYOK slots (kept in memory only)
        self.base_url: str | None = None
        self.findings: dict[str, Finding] = {}
        self.risk_peak = 0
        self.late_tasks: list[asyncio.Task] = []
        self.coach_used: dict[str, int] = {}


def new_session(scenario_id: str, requested: str) -> Session:
    """Decide live vs replay (keys, REPLAY_ONLY, one live session at a time, daily cap)."""
    mode, reason = "replay", None
    if requested == "live":
        if not settings.live_capable:
            reason = "Live checking is not available right now."
        elif _live_active is not None:
            reason = "Another live call is running; showing the recorded run."
        elif not assets.has_audio(scenario_id):
            reason = "No call audio for this case."
        elif not db.try_take_slot(settings.daily_session_cap):
            reason = "Live capacity reached today — showing recorded run."
        else:
            mode = "live"
    s = Session(scenario_id, mode, reason)
    SESSIONS[s.id] = s
    db.log_session_start(s.id, scenario_id, mode, _now())
    return s


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def start(s: Session) -> None:
    if s.task is None:
        s.task = asyncio.create_task(_run(s))


def stop(s: Session) -> None:
    if s.task and not s.task.done():
        s.task.cancel()


def tokens_for(first_index: int, text: str) -> list[dict]:
    """Token objects for one segment; `i` continues across the segments of a turn."""
    out = []
    for k, (w, _, _) in enumerate(tokenize(text)):
        lang = "hi" if any("ऀ" <= ch <= "ॿ" for ch in w) else "en"
        out.append({"i": first_index + k, "w": w, "lang": lang})
    return out


def summary(s: Session, stopped: bool = False) -> dict:
    by_rule: dict[str, int] = {}
    for f in s.findings.values():
        if f.kind != "good_practice":
            by_rule[f.rule_id] = by_rule.get(f.rule_id, 0) + 1
    return {"risk_peak": s.risk_peak, "findings_count": sum(by_rule.values()), "by_rule": by_rule, "stopped": stopped}


async def _run(s: Session) -> None:
    global _live_active
    try:
        async with asyncio.timeout(settings.session_max_s):
            if s.effective_mode == "live":
                _live_active = s.id
                try:
                    await _run_live(s)
                except SttError as e:
                    log.warning("session=%s stt failed: %s", s.id, e)
                    _live_active = None  # the recorded tail does not use Gnani or the LLM: free the live slot
                    await _switch_to_replay(s)
            else:
                await _run_replay(s)
    except asyncio.CancelledError:
        s.log.emit("session.ended", {"summary": summary(s, stopped=True)})
        raise
    except TimeoutError:
        s.log.emit("error", {"code": "session_timeout", "message_user": "The demo call ran too long and was stopped.",
                             "retryable": True})
    except Exception:
        log.exception("session=%s failed", s.id)
        s.log.emit("error", {"code": "internal", "message_user": "Something went wrong. Please try the recorded run.",
                             "retryable": True})
    finally:
        if _live_active == s.id:
            _live_active = None
        _finish(s)


def _finish(s: Session) -> None:
    db.log_session_end(s.id, _now(), s.risk_peak)
    last = s.log.events[-1] if s.log.events else {}
    done = last.get("type") == "session.ended" and not last["data"]["summary"].get("stopped")
    if settings.record_runs and s.effective_mode == "live" and done:
        replay.save(f"_runs/{s.scenario_id}_{s.id}", s.log.events)
    s.log.close()


# ---------------------------------------------------------------- replay
def _store_finding(s: Session, d: dict) -> None:
    db.log_finding(s.id, d)
    s.findings[d["id"]] = Finding(id=d["id"], turn_idx=d["turn_idx"], rule_id=d["rule_id"], kind=d["kind"],
                                  confidence=d["confidence"])


def _absorb(s: Session, events: list[dict]) -> None:
    """Keep the log tables and the summary in step with a replayed stream."""
    for e in events:
        if e["type"] == "finding.detected":
            _store_finding(s, e["data"])
        elif e["type"] == "risk.update":
            s.risk_peak = max(s.risk_peak, e["data"]["score"])


async def _run_replay(s: Session) -> None:
    events = replay.load(s.scenario_id)
    if events is None:
        s.log.emit("error", {"code": "no_replay", "message_user": "No recorded run exists for this case.",
                             "retryable": False})
        return
    await replay.play(events, s.log.push)
    _absorb(s, events)


async def _switch_to_replay(s: Session) -> None:
    """Prisma failed twice: show the recorded run for the rest of the call (docs/01 §3)."""
    events = replay.load(s.scenario_id)
    if events is None:
        s.log.emit("error", {"code": "stt_unavailable", "retryable": True,
                             "message_user": "Speech service is not responding. Please try again later."})
        return
    s.effective_mode = "replay"
    s.log.emit("banner", {"kind": "replay", "message": "Live transcription is unavailable, showing the recorded run."})
    after = max((e["data"].get("turn_idx", 0) for e in s.log.events if e["type"] == "turn.ended"), default=0)
    rest = replay.remaining(events, after)
    await replay.play(rest, lambda e: s.log.emit(e["type"], e["data"]))
    _absorb(s, rest)


# ---------------------------------------------------------------- live
async def _segments(client: httpx.AsyncClient, wav, profile: dict, key: str):
    """Realtime first. If it fails (before or during the turn) the turn is retried ONCE over REST with the same profile,
    continuing after the segments already delivered. If REST fails too, SttError (the caller falls back to replay)."""
    got, covered = 0, 0
    if settings.stt_mode == "realtime":
        try:
            gen = realtime.stream_turn(wav, profile, key)
            while True:
                try:
                    seg = await asyncio.wait_for(anext(gen), FIRST_SEGMENT_S if got == 0 else None)
                except StopAsyncIteration:
                    if got:
                        return
                    log.warning("realtime stt ended without any segment, retrying over REST")
                    break
                got, covered = got + 1, seg.audio_end_ms
                yield seg
        except (SttError, TimeoutError) as e:
            log.warning("realtime stt failed after %d segments, retrying over REST: %s %s", got, type(e).__name__,
                        e.__cause__ or e)
    start = retry_start_ms(got, covered, rest_tried=False)
    for seg in await stt_rest.transcribe_turn(client, wav, profile, key, start or 0, got):
        if seg.text or got == 0:  # nothing left to transcribe after the delivered segments is not an error
            yield seg


async def _run_live(s: Session) -> None:
    sc = assets.scenarios()[s.scenario_id]
    turns = assets.audio_manifest()[s.scenario_id]["turns"]
    ctx = assets.context_for(sc)
    key = s.api_key or settings.gnani_api_key_id
    s.log.emit("session.started", {"scenario_id": s.scenario_id, "effective_mode": "live", "turns_total": len(turns),
                                   "simulated_start_time": ctx.simulated_start_time})
    s.log.emit("stage.status", {"stage": "connecting", "turn_idx": 0, "text": "Connecting"})
    history: list[Turn] = []
    score, spoken = 0, 0
    llm_client = llm.make_client()
    warm = asyncio.create_task(llm.warm_up(llm_client, s.api_key, s.base_url))
    try:
        async with httpx.AsyncClient(timeout=30) as stt_client:
            for n, t in enumerate(turns):
                idx, role = t["idx"], assets.SPEAKER[t["speaker"]]
                s.log.emit("turn.started", {"turn_idx": idx, "speaker": role, "audio_url": "/audio/" + t["mp3"],
                                            "duration_ms": t["duration_ms"]})
                s.log.emit("stage.status", {"stage": "transcribing", "turn_idx": idx, "text": "Transcribing"})
                turn = LiveTurn(s, ctx, history, idx, t["speaker"], llm_client)
                async with gnani_lock():  # one active Gnani request per key
                    async for seg in _segments(stt_client, settings.data_dir / "audio" / t["wav8k"], load_profile(role), key):
                        turn.on_segment(seg)
                score = await turn.finish(score)
                s.log.emit("turn.ended", {"turn_idx": idx})
                history.append(Turn(speaker=t["speaker"], text=turn.text))
                db.log_turn(s.id, idx, t["speaker"], turn.text, turn.lang, turn.stt_ms)
                if turn.nudge and not turn.nudge_late and spoken < MAX_SPOKEN_PER_CALL:
                    spoken += 1
                    s.log.emit("coach.speak", {"audio_url": turn.nudge["audio_url"], "duration_ms": turn.nudge["duration_ms"]})
                    if settings.coach_mode == "hold":  # the call waits while the coach speaks
                        await asyncio.sleep((turn.nudge["duration_ms"] + COACH_GAP_MS) / 1000)
                if n + 1 < len(turns):  # the natural pause between turns, from the audio schedule
                    gap = turns[n + 1]["offset_ms"] - t["offset_ms"] - t["duration_ms"]
                    await asyncio.sleep(max(0, gap) / 1000 * settings.pace)
            if s.late_tasks:  # late deep answers (up to the 8 s LLM budget) still update the call
                await asyncio.gather(*s.late_tasks, return_exceptions=True)
    finally:
        warm.cancel()
        for task in s.late_tasks:  # stopped or timed out: no LLM answer may arrive after the client is closed
            task.cancel()
        await llm_client.aclose()
    s.log.emit("session.ended", {"summary": summary(s)})


class LiveTurn:
    """One turn: segments so far, findings known, the nudge, and the LLM tasks in flight."""

    def __init__(self, s: Session, ctx, history: list[Turn], idx: int, speaker: str, llm_client) -> None:
        self.s, self.ctx, self.history, self.idx, self.speaker, self.llm_client = s, ctx, history, idx, speaker, llm_client
        self.role = assets.SPEAKER[speaker]
        self.text, self.lang, self.stt_ms, self.ntok = "", "", 0, 0
        self.known: dict[str, Finding] = {}
        self.nudge: dict | None = None
        self.nudge_late = False
        self.closed = False
        self.tasks: list[asyncio.Task] = []
        self.score_before = 0
        self.last_arrival = 0.0
        self.n_segments, self.saw_last = 0, False

    def close_segments(self) -> None:
        """The STT stream can end without marking its last segment: close the turn's transcript explicitly."""
        if self.n_segments and not self.saw_last:
            self.s.log.emit("transcript.final", {
                "turn_idx": self.idx, "segment_idx": self.n_segments, "speaker": self.role, "text": "",
                "lang_detected": self.lang, "tokens": [], "is_last_segment_of_turn": True,
                "stt_latency_ms": 0, "source": "live"})
            self.saw_last = True

    def on_segment(self, seg: TranscriptSegment) -> None:
        now = time.perf_counter()
        self.n_segments, self.saw_last = max(self.n_segments, seg.segment_idx + 1), self.saw_last or seg.is_last
        seg_end = seg.stream_t0 + seg.audio_end_ms / 1000 * settings.pace
        toks = tokens_for(self.ntok, seg.text)
        self.ntok += len(toks)
        self.text = f"{self.text} {seg.text}".strip()
        self.lang, self.stt_ms = seg.lang or self.lang, max(self.stt_ms, seg.latency_ms)
        self.s.log.emit("transcript.final", {
            "turn_idx": self.idx, "segment_idx": seg.segment_idx, "speaker": self.role, "text": seg.text,
            "lang_detected": seg.lang, "tokens": toks, "is_last_segment_of_turn": seg.is_last,
            "stt_latency_ms": seg.latency_ms, "source": "live"})
        if self.speaker != "A":
            return
        self.last_arrival = now
        self.s.log.emit("finding.pending", {"turn_idx": self.idx, "segment_idx": seg.segment_idx})
        self.s.log.emit("stage.status", {"stage": "checking", "turn_idx": self.idx, "text": "Checking against the rulebook"})
        box: dict = {}
        if settings.check_granularity == "segment" or seg.is_last:
            task = asyncio.create_task(self._deep(box, self.text, seg, seg_end, now))  # starts at arrival, in parallel
            self.tasks.append(task)
            self.s.late_tasks.append(task)
        t0 = time.perf_counter()
        fast = fast_findings(self.ctx, self.history, self.idx, self.text)
        box["fast"] = fast  # set before the task's first await completes
        prefilter_ms = int((time.perf_counter() - t0) * 1000)
        self._handle(fast, "fast", {"stt_ms": seg.latency_ms, "prefilter_ms": prefilter_ms, "llm_ms": 0}, seg_end)

    async def _deep(self, box: dict, text: str, seg: TranscriptSegment, seg_end: float, arrived: float) -> None:
        out, llm_ms = await llm.review(self.llm_client, self.ctx, self.history[-2:], text, self.s.api_key, self.s.base_url)
        if out is None:
            self.s.log.emit("banner", {"kind": "llm_degraded",
                                       "message": "Reduced checking: the language model did not answer in time."})
            return
        late = time.perf_counter() - arrived > FIRST_ANSWER_S
        deep = deep_findings(self.ctx, box["fast"], out, self.idx, text)
        self._handle(deep, "deep", {"stt_ms": seg.latency_ms, "prefilter_ms": 0, "llm_ms": llm_ms}, seg_end, late=late)
        if self.closed:  # the answer came after the turn closed: correct the risk meter
            self._risk(self.score_before)

    def _handle(self, findings: list[Finding], phase: str, lat: dict, seg_end: float, late: bool = False) -> None:
        """Emit new findings, or ones that became stronger; same stable id = update in place."""
        for f in findings:
            old = self.known.get(f.id)
            if old and (_RANK[f.kind], f.confidence) <= (_RANK[old.kind], old.confidence):
                continue
            self.known[f.id] = f
            d = f.model_dump()
            lat_full = {**lat, "total_ms": int((time.perf_counter() - seg_end) * 1000)}
            d.update(token_range=list(f.token_range), phase=phase, rbi_ref=assets.rbi_ref(f.rule_id), late=late,
                     source="prefilter" if f.source == "gate" else f.source, latency=lat_full)
            self.s.log.emit("finding.detected", d)
            _store_finding(self.s, d)
            if f.kind == "violation" and self.nudge is None:
                self._nudge(f, lat_full)

    def _nudge(self, f: Finding, lat: dict) -> None:
        line = assets.coach_line(f.rule_id, self.s.coach_used.get(f.rule_id, 0))
        if line is None:
            return
        self.s.coach_used[f.rule_id] = self.s.coach_used.get(f.rule_id, 0) + 1
        self.nudge, self.nudge_late = line, self.closed  # a card shown after the turn ended gets no voice
        self.s.log.emit("stage.status", {"stage": "coaching", "turn_idx": self.idx, "text": "Coach"})
        self.s.log.emit("coach.nudge", {"finding_id": f.id, "rule_id": f.rule_id, "text": line["text"],
                                        "audio_url": line["audio_url"], "duck": settings.coach_mode == "duck",
                                        "latency": lat})

    def _risk(self, before: int) -> int:
        upd = risk.update(before, list(self.known.values()))
        self.s.log.emit("risk.update", upd.model_dump())
        self.s.risk_peak = max(self.s.risk_peak, upd.score)
        return upd.score

    async def finish(self, score_before: int) -> int:
        """Wait for the first LLM answers (4 s), then close the turn with its risk update. Returns the new score."""
        self.score_before = score_before
        self.close_segments()
        if self.speaker != "A":
            return score_before
        if self.tasks:
            left = max(0.0, FIRST_ANSWER_S - (time.perf_counter() - self.last_arrival))
            await asyncio.wait(self.tasks, timeout=left)
        self.closed = True
        return self._risk(score_before)
