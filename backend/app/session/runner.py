"""Session runner: one asyncio task per session; live (Prisma + engine) or replay. Event order: docs/02 §2 as changed by docs/13."""
import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime

import httpx2 as httpx

from .. import db, replay
from .. import schedule as rules_clock
from ..config import settings
from ..rules import llm, risk, skip
from ..rules.engine import deep_findings, fast_findings
from ..rules.schemas import Finding, Turn
from ..rules.text import tokenize
from ..security.credentials import Creds
from ..stt import realtime
from ..stt import rest as stt_rest
from ..stt.base import (
    SttAuthError,
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
COACH_GAP_MS = rules_clock.COACH_HOLD_GAP_MS
MAX_SPOKEN_PER_CALL = 3
_RANK = {"good_practice": 0, "advisory": 1, "needs_review": 2, "violation": 3}

SESSIONS: dict[str, "Session"] = {}
_live_active: set[str] = set()  # ids of running live sessions (at most settings.max_live_sessions)
MAX_SESSIONS_KEPT = 400
UNSTARTED_TTL_S = 90  # a session whose WebSocket never connects drops its keys after this long


class Session:
    def __init__(self, scenario_id: str, mode: str, reason: str | None = None, creds: Creds | None = None,
                 pause_for_coach: bool = False) -> None:
        self.id = uuid.uuid4().hex[:10]
        self.scenario_id, self.effective_mode, self.reason = scenario_id, mode, reason
        self.log = EventLog()
        self.task: asyncio.Task | None = None
        self.voice_nudge = None  # set by the live run: called when a nudge should be spoken
        self.resume_ms = 0  # where the call clock stood when live transcription failed (natural time)
        self.pause_for_coach = pause_for_coach  # the user's option: the call waits while a coach clip plays
        self.creds = creds  # the visitor's keys (memory only; wiped when the session ends)
        self.visitor = creds is not None  # a visitor session never falls back to the server's keys
        self.llm_error = ""  # last plain-language reason the language model failed
        self.findings: dict[str, Finding] = {}
        self.risk_peak = 0
        self.late_tasks: list[asyncio.Task] = []
        self.coach_used: dict[str, int] = {}
        self.llm_skipped = 0  # LLM reviews skipped by the short-segment guard (not the same as a clean review)


def new_session(scenario_id: str, requested: str, creds: Creds | None = None, pause_for_coach: bool = False) -> Session:
    """Decide live vs replay (REPLAY_ONLY, concurrent live limit, audio). A live request needs keys: the caller checks."""
    mode, reason = "replay", None
    if requested == "live":
        if not settings.live_capable:
            reason = "Live checking is not available right now."
        elif len(_live_active) >= settings.max_live_sessions:
            reason = "All live call slots are busy right now; showing the recorded run."
        elif not assets.has_audio(scenario_id):
            reason = "No call audio for this case."
        else:
            mode = "live"
    if mode != "live" and creds is not None:
        creds.wipe()  # a recorded run needs no keys: do not keep them
        creds = None
    _prune()
    s = Session(scenario_id, mode, reason, creds, pause_for_coach)
    SESSIONS[s.id] = s
    db.log_session_start(s.id, scenario_id, mode, _now())
    if mode == "live":
        _live_active.add(s.id)  # the slot is held from creation, so a burst cannot exceed the limit
        asyncio.get_running_loop().call_later(UNSTARTED_TTL_S, _expire_unstarted, s)
    return s


def _prune() -> None:
    """Keep the in-memory session table bounded: drop the oldest finished sessions."""
    if len(SESSIONS) >= MAX_SESSIONS_KEPT:
        for sid in [k for k, v in SESSIONS.items() if v.task is not None and v.task.done()][:MAX_SESSIONS_KEPT // 4]:
            del SESSIONS[sid]


def _expire_unstarted(s: Session) -> None:
    """A live session whose WebSocket never connected gives up its slot and its keys."""
    if s.task is None:
        _live_active.discard(s.id)
        SESSIONS.pop(s.id, None)
        if s.creds is not None:
            s.creds.wipe()
            s.creds = None


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
    try:
        async with asyncio.timeout(settings.session_max_s):
            if s.effective_mode == "live":
                _live_active.add(s.id)
                try:
                    await _run_live(s)
                except SttAuthError as e:  # the visitor's Gnani key was refused: say so, never fall back to ours
                    log.warning("session=%s gnani key rejected: %s", s.id, e)
                    s.log.emit("error", {"code": "gnani_key_rejected", "retryable": False, "message_user":
                               "Your Gnani key was rejected. Check it in Settings, or play the recorded run."})
                except SttError as e:
                    log.warning("session=%s stt failed: %s", s.id, e)
                    _live_active.discard(s.id)  # the recorded tail does not use Gnani or the LLM: free the live slot
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
        _live_active.discard(s.id)
        _finish(s)


def _finish(s: Session) -> None:
    if s.creds is not None:
        s.creds.wipe()
        s.creds = None
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


def _turns(scenario_id: str, base_ms: int = 0) -> list[dict]:
    """The call's turns on the natural audio schedule (speaker, offset, duration), offsets counted from `base_ms`."""
    return [{**t, "offset_ms": t["offset_ms"] - base_ms} for t in assets.audio_manifest().get(scenario_id, {}).get("turns", [])]


async def _run_replay(s: Session) -> None:
    events = replay.load(s.scenario_id)
    if events is None:
        s.log.emit("error", {"code": "no_replay", "message_user": "No recorded run exists for this case.",
                             "retryable": False})
        return
    planned = await replay.play(events, s.log.push, turns=_turns(s.scenario_id), hold=s.pause_for_coach)
    if planned:
        log.info("session=%s replay: agent started without the nudge ready %d time(s)", s.id, planned.agent_started_anyway)
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
    # Time zero is now: turns the live clock has not reached yet start at their schedule minus where the call stands;
    # turns already started are re-sent at once (the screen does not restart their audio).
    await replay.play(rest, lambda e: s.log.emit(e["type"], e["data"]),
                      turns=_turns(s.scenario_id, s.resume_ms), hold=s.pause_for_coach)
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
        except SttAuthError:
            raise  # a refused key is not retried over REST
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
    creds = s.creds
    if creds is None and (s.visitor or not settings.server_keys):
        s.log.emit("error", {"code": "keys_required", "retryable": False, "message_user":
                   "Add your keys in Settings to start a live call, or play the recorded run."})
        return
    key = creds.gnani_key if creds else settings.gnani_api_key_id
    s.log.emit("session.started", {"scenario_id": s.scenario_id, "effective_mode": "live", "turns_total": len(turns),
                                   "simulated_start_time": ctx.simulated_start_time})
    s.log.emit("stage.status", {"stage": "connecting", "turn_idx": 0, "text": "Connecting"})
    history: list[Turn] = []
    spoken = 0  # coach clips reserved so far (cap per call)
    shift_s = 0.0  # how far the call clock runs from the natural schedule (agent waits for the coach, pause option)
    t0 = time.perf_counter()
    order = [t["idx"] for t in turns]
    info = {t["idx"]: t for t in turns}
    started = {i: asyncio.Event() for i in order}
    settled = {i: asyncio.Event() for i in order}  # the turn's checks are closed
    voiced = {i: asyncio.Event() for i in order}  # a spoken nudge exists for the turn
    start_at: dict[int, float] = {}
    coaching: dict[int, dict] = {}
    last_coach_end = -1e9
    agent_anyway = 0  # the agent started after the 2 s wait without the nudge being ready
    closing: list[asyncio.Task] = []
    coach_tasks: list[asyncio.Task] = []
    llm_client = llm.make_client()
    warm = asyncio.create_task(llm.warm_up(llm_client, creds))

    async def sleep_until(target) -> None:
        while (left := (target() if callable(target) else target) - time.perf_counter()) > 0:
            await asyncio.sleep(left)

    def natural_target(nat: float):
        return lambda: nat + shift_s  # shift_s can grow while we wait (pause option)

    async def agent_due(k: int, m: int, nat_due: float) -> float:
        """When agent turn `m` starts, given the earlier agent turn `k` (rules: schedule.py). Absolute time."""
        nonlocal agent_anyway
        clip = coaching.get(k)
        deadline = nat_due + rules_clock.AGENT_WAIT_S
        if clip is None:  # wait for the check of turn k to settle or a nudge to appear, at most 2 s past the natural start
            waits = [asyncio.ensure_future(voiced[k].wait()), asyncio.ensure_future(settled[k].wait())]
            done, pending = await asyncio.wait(waits, timeout=max(0.0, deadline - time.perf_counter()),
                                               return_when=asyncio.FIRST_COMPLETED)
            for p in pending:
                p.cancel()
            if not done:
                agent_anyway += 1
                return deadline
            clip = coaching.get(k)
            if clip is None:
                return nat_due
        try:
            await asyncio.wait_for(clip["done"].wait(), 30)  # the clip plays under the next speaker, then the agent follows
        except TimeoutError:
            return nat_due
        nxt = order[order.index(k) + 1]
        floor = start_at[nxt] + info[nxt]["duration_ms"] / 1000 + rules_clock.MIN_FILE_GAP_S if nxt != m else 0.0
        return max(clip["end"] + rules_clock.AGENT_AFTER_COACH_S, floor)

    async def clock() -> None:
        """The call itself: turns start on the natural audio schedule, whatever transcription and checking are doing.
        Only a coach nudge moves the agent's next turn (it follows the clip); the audio never pauses."""
        nonlocal shift_s
        prev_agent = None
        for t in turns:
            idx = t["idx"]
            nat = t0 + t["offset_ms"] / 1000 * settings.pace
            if t["speaker"] == "A" and prev_agent is not None and not s.pause_for_coach:
                due = await agent_due(prev_agent, idx, nat + shift_s)
                await sleep_until(due)
            else:
                await sleep_until(natural_target(nat))
            start_at[idx] = time.perf_counter()
            shift_s = start_at[idx] - nat
            s.log.emit("turn.started", {"turn_idx": idx, "speaker": assets.SPEAKER[t["speaker"]],
                                        "audio_url": "/audio/" + t["mp3"], "duration_ms": t["duration_ms"]})
            started[idx].set()
            if t["speaker"] == "A":
                prev_agent = idx

    async def run_coach(k: int, clip: dict) -> None:
        """Play the nudge under the next speaker's turn (or when it is ready, if later). Rules: schedule.py."""
        nonlocal last_coach_end, shift_s
        i = order.index(k)
        nxt = order[i + 1] if i + 1 < len(order) else None
        if nxt is not None and info[nxt]["speaker"] != info[k]["speaker"]:
            await started[nxt].wait()
            at = start_at[nxt] + rules_clock.COACH_DELAY_S
        else:  # last turn of the call, or the same speaker again: after the turn ended
            at = start_at[k] + info[k]["duration_ms"] / 1000 + rules_clock.COACH_LAST_TURN_GAP_S
        await sleep_until(lambda: max(at, clip["ready"], last_coach_end + rules_clock.COACH_QUEUE_GAP_S))
        line = clip["line"]
        s.log.emit("coach.speak", {"audio_url": line["audio_url"], "duration_ms": line["duration_ms"]})
        clip["end"] = time.perf_counter() + line["duration_ms"] / 1000
        last_coach_end = clip["end"]
        clip["done"].set()
        if s.pause_for_coach:  # the user's option: the call waits while the coach speaks
            shift_s += (line["duration_ms"] + COACH_GAP_MS) / 1000

    def voice_nudge(turn: "LiveTurn") -> None:
        nonlocal spoken
        if spoken >= MAX_SPOKEN_PER_CALL or turn.idx in coaching:
            return
        spoken += 1
        clip = {"line": turn.nudge, "ready": time.perf_counter(), "done": asyncio.Event(), "end": 0.0}
        coaching[turn.idx] = clip
        voiced[turn.idx].set()
        coach_tasks.append(asyncio.create_task(run_coach(turn.idx, clip)))

    s.voice_nudge = voice_nudge

    async def close_turn(turn: LiveTurn, idx: int, prev: asyncio.Task | None) -> int:
        """Close one turn once the previous one is closed (risk follows the order of the call); never blocks the call."""
        score = await turn.finish(await prev if prev else 0)
        s.log.emit("turn.ended", {"turn_idx": idx})
        settled[idx].set()
        return score

    ticker = asyncio.create_task(clock())
    try:
        async with httpx.AsyncClient(timeout=30) as stt_client:
            for t in turns:
                idx, role = t["idx"], assets.SPEAKER[t["speaker"]]
                await started[idx].wait()  # the audio of this turn is playing now
                s.log.emit("stage.status", {"stage": "transcribing", "turn_idx": idx, "text": "Transcribing"})
                turn = LiveTurn(s, ctx, list(history), idx, t["speaker"], llm_client)
                async with gnani_lock(key):  # one active Gnani request per key
                    async for seg in _segments(stt_client, settings.data_dir / "audio" / t["wav8k"], load_profile(role), key):
                        turn.on_segment(seg)
                history.append(Turn(speaker=t["speaker"], text=turn.text))
                db.log_turn(s.id, idx, t["speaker"], turn.text, turn.lang, turn.stt_ms)
                closing.append(asyncio.create_task(close_turn(turn, idx, closing[-1] if closing else None)))
            await asyncio.gather(*closing)
            if s.late_tasks:  # late deep answers (up to the 8 s LLM budget) still update the call
                await asyncio.gather(*s.late_tasks, return_exceptions=True)
            await asyncio.gather(*coach_tasks)  # a nudge on the last turn plays before the call ends
            last = turns[-1]
            end_at = max([start_at[last["idx"]] + last["duration_ms"] / 1000, *(c["end"] for c in coaching.values())])
            await sleep_until(end_at)  # the call is not over until its last audio is
            if agent_anyway:
                log.info("session=%s agent started without the nudge ready %d time(s)", s.id, agent_anyway)
    except SttError:  # let the turns already heard close properly before the recorded tail takes over
        s.resume_ms = int((time.perf_counter() - t0 - shift_s) * 1000)
        ticker.cancel()
        for task in coach_tasks:
            task.cancel()
        await asyncio.gather(*closing, return_exceptions=True)
        raise
    finally:
        warm.cancel()
        ticker.cancel()
        s.voice_nudge = None
        for task in [*closing, *coach_tasks, *s.late_tasks]:  # stopped or timed out: nothing may arrive after the client is closed
            task.cancel()
        await llm_client.aclose()
    log.info("session=%s llm_skipped=%d | process totals: llm_calls=%d llm_cache_hits=%d", s.id, s.llm_skipped,
             llm.STATS["calls"], llm.STATS["cache_hits"])
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
        if self.s.visitor and self.s.creds is None:
            return  # keys already wiped: never fall through to the server's key
        if skip.should_skip(self.ctx, self.history, text, box["fast"]):
            self.s.llm_skipped += 1
            log.info("llm skipped session=%s turn=%s words=%d (short, no prefilter hit, no keyword)",
                     self.s.id, self.idx, len(text.split()))
            return
        out, llm_ms = await llm.review(self.llm_client, self.ctx, self.history[-2:], text, self.s.creds,
                                     on_error=lambda m: setattr(self.s, "llm_error", m))
        if out is None:
            why = self.s.llm_error or "The language model did not answer in time."
            self.s.log.emit("banner", {"kind": "llm_degraded",
                                       "message": f"Language model unavailable, showing fast checks only. {why}"})
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
                                        "audio_url": line["audio_url"], "latency": lat})
        if not self.nudge_late and self.s.voice_nudge is not None:  # a card shown after the turn ended gets no voice
            self.s.voice_nudge(self)

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
