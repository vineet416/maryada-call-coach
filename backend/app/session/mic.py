"""Speak live: the visitor speaks as the agent into the microphone. Audio arrives as binary WebSocket frames (8 kHz PCM16), the
TurnSplitter cuts it into agent turns, each turn goes to its own Prisma socket (same adapter as the recorded-audio live path), and
the same engine, coach and risk code judge the text. Nothing is stored: no audio on disk, no database rows, no recording; events
stay in memory for the report only (settings.mic_events_ttl_s). Keys come from the sessions POST body, are never logged, and there
is no recorded tail to fall back to."""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime

from .. import report
from .. import schedule as rules_clock
from ..config import settings
from ..rules import llm
from ..rules.loader import load_rules
from ..rules.schemas import CallContext, Turn
from ..security.credentials import Creds
from ..stt.base import LiveAudio, SttAuthError, SttError, SttGate, load_profile
from . import assets
from .mic_rules import (
    ANSWERED_BY,
    IST,
    FrameLimiter,
    ist_hhmm,
    reminder_due,
    valid_frame,
)
from .runner import (
    MAX_SPOKEN_PER_CALL,
    PREV_TURN_S,
    SESSIONS,
    UNSTARTED_TTL_S,
    LiveTurn,
    Session,
    _expire_unstarted,
    _live_active,
    _prune,
    _segments,
    summary,
)
from .turn_split import TurnSplitter

log = logging.getLogger("maryada.mic")

NO_FRAMES_S = 10.0  # no audio frame for this long (also: no connection) ends the call
POLL_S = 0.25  # the main loop checks its exits at least this often
FINISH_S = 30.0  # longest wait for the last turns' transcripts and checks after the call ends
COACH_TAIL_S = 0.3  # the microphone counts as silent this long after a coach clip ends (room echo)
MAX_FAILED_TURNS = 3  # this many turns in a row with no text from speech recognition end the call
QUEUE_FRAMES = 400  # about 25 s of audio waiting for the main loop; more is dropped


class MicUnavailable(Exception):
    """A Speak live call cannot start now (live calls off, or all slots busy). The message is for the visitor."""


@dataclass
class MicState:
    ctx: CallContext
    clock: str | None
    started: datetime
    frames: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(QUEUE_FRAMES))
    limiter: FrameLimiter = field(default_factory=FrameLimiter)
    end: asyncio.Event = field(default_factory=asyncio.Event)
    last_frame: float = field(default_factory=time.monotonic)
    coach_until: float = 0.0  # perf_counter time until which microphone frames are treated as silence
    reminded: bool = False
    dropped: int = 0


def new_mic_session(creds: Creds | None, clock: str | None = None) -> Session:
    """Create a Speak live session and hold one live slot for it. The caller has checked the keys and the clock."""
    if not settings.live_capable:
        raise MicUnavailable("Live checking is not available right now.")
    if len(_live_active) >= settings.max_live_sessions:
        raise MicUnavailable("All live call slots are busy right now. Try again in a minute.")
    _prune()
    s = Session("mic", "mic", None, creds)
    s.mic = MicState(CallContext(answered_by="unknown"), clock, datetime.now(IST))
    SESSIONS[s.id] = s
    _live_active.add(s.id)
    asyncio.get_running_loop().call_later(UNSTARTED_TTL_S, _expire_unstarted, s)
    return s


def on_frame(s: Session, data: bytes) -> None:
    """One binary WebSocket message from the visitor's browser."""
    m = s.mic
    if m is None or s.log.done:
        return
    m.last_frame = time.monotonic()
    if not valid_frame(len(data)) or not m.limiter.allow(len(data), m.last_frame):
        m.dropped += 1
        return
    try:
        m.frames.put_nowait(data)
    except asyncio.QueueFull:
        m.dropped += 1


def handle_control(s: Session, msg: dict) -> None:
    """A JSON control message: end (finish gracefully), set_answered_by, barge_in (the visitor speaks over the coach clip)."""
    m = s.mic
    if m is None or s.log.done:
        return
    kind = msg.get("type")
    if kind == "end":
        m.end.set()
    elif kind == "set_answered_by" and msg.get("value") in ANSWERED_BY:
        m.ctx.answered_by = msg["value"]
        s.log.emit("context.updated", {"answered_by": m.ctx.answered_by})
    elif kind == "barge_in":
        m.coach_until = 0.0


def build_session_report(s: Session) -> dict:
    """The call report of a finished Speak live call, from its in-memory events (same builder as a recorded run)."""
    m, events = s.mic, s.log.events
    offsets = {e["data"]["turn_idx"]: e["t_ms"] for e in events if e["type"] == "turn.started"}
    ended = next((e["t_ms"] for e in reversed(events) if e["type"] == "session.ended"), s.log.now_ms())
    meta = {"id": s.id, "title": "Speak live call", "date": m.started.date().isoformat(), "time": m.ctx.simulated_start_time,
            "duration_ms": ended, "turn_offsets": offsets}
    return report.build_report(events, meta, load_rules()["rules"], "live")


async def run_mic(s: Session) -> None:
    key = s.creds.gnani_key if s.creds else settings.gnani_api_key_id
    if s.creds is None and not settings.server_keys:
        s.log.emit("error", {"code": "keys_required", "retryable": False, "message_user":
                             "Add your keys in Settings to start a Speak live call."})
        return
    await _MicCall(s, key).run()


class _MicCall:
    def __init__(self, s: Session, key: str) -> None:
        self.s, self.m, self.key = s, s.mic, key
        self.ctx = s.mic.ctx
        self.t0 = time.perf_counter()
        self.idx = 0  # turns started so far (1-based ids)
        self.agent_turns = 0  # turns that produced text
        self.history: list[Turn] = []
        self.splitter = TurnSplitter()
        self.cur: LiveAudio | None = None  # the audio of the turn the visitor is speaking now
        self.client = llm.make_client()
        self.gate = SttGate(label=s.id)
        s.stt_gate = self.gate
        self.turn_tasks: list[asyncio.Task] = []
        self.closing: list[asyncio.Task] = []
        self.coach_tasks: list[asyncio.Task] = []
        self.prev_done: asyncio.Event | None = None
        self.turn_over: dict[int, asyncio.Event] = {}  # the visitor stopped speaking in this turn
        self.ended_at: dict[int, float] = {}
        self.coaching: set[int] = set()
        self.spoken = 0
        self.last_coach_end = -1e9
        self.failed_in_a_row = 0
        self.fatal = False

    async def run(self) -> None:
        s, m = self.s, self.m
        self.ctx.simulated_start_time = m.clock or ist_hhmm()  # R1 reads this on the first agent turn
        m.last_frame = time.monotonic()
        s.log.emit("session.started", {"scenario_id": "mic", "effective_mode": "mic", "turns_total": 0,
                                       "simulated_start_time": self.ctx.simulated_start_time})
        s.log.emit("context.updated", {"answered_by": self.ctx.answered_by})
        s.log.emit("stage.status", {"stage": "listening", "turn_idx": 0, "text": "Listening"})
        warm = asyncio.create_task(llm.warm_up(self.client, s.creds))
        s.voice_nudge = self.voice_nudge
        try:
            reason = await self._listen()
            await self._finish(reason)
        finally:
            warm.cancel()
            s.voice_nudge = None
            for task in [*self.turn_tasks, *self.closing, *self.coach_tasks, *s.late_tasks]:
                task.cancel()
            await self.client.aclose()
            log.info("session=%s mic call over: turns=%d dropped_frames=%d llm_skipped=%d", s.id, self.idx, m.dropped, s.llm_skipped)

    async def _listen(self) -> str:
        """Feed frames to the splitter until the visitor ends the call, the time limit, silence on the line, or a fatal failure."""
        m = self.m
        while True:
            if m.end.is_set():
                return "end"
            if self.fatal:
                return "failed"
            if time.perf_counter() - self.t0 >= settings.mic_session_max_s:
                return "limit"
            if time.monotonic() - m.last_frame >= NO_FRAMES_S:
                return "no_audio"
            try:
                pcm = await asyncio.wait_for(m.frames.get(), POLL_S)
            except TimeoutError:
                continue
            if time.perf_counter() < m.coach_until:  # the coach clip is playing: the room may echo it, so this is silence
                pcm = bytes(len(pcm))
            for kind, val in self.splitter.feed(pcm):
                self._apply(kind, val)

    def _apply(self, kind: str, val: object) -> None:
        if kind == "start":
            self._start_turn()
        elif kind == "audio" and self.cur is not None:
            self.cur.feed(val)  # type: ignore[arg-type]
        elif kind == "end" and self.cur is not None:
            self.cur.close()
            self.ended_at[self.idx] = time.perf_counter()
            self.turn_over[self.idx].set()
            self.cur = None

    def _start_turn(self) -> None:
        self.idx += 1
        audio, done = LiveAudio(), asyncio.Event()
        self.cur = audio
        self.turn_over[self.idx] = asyncio.Event()
        self.s.log.emit("turn.started", {"turn_idx": self.idx, "speaker": "agent", "audio_url": "", "duration_ms": 0})
        self.s.log.emit("stage.status", {"stage": "transcribing", "turn_idx": self.idx, "text": "Transcribing"})
        self.turn_tasks.append(asyncio.create_task(self._transcribe(self.idx, audio, self.prev_done, done, time.perf_counter())))
        self.prev_done = done

    async def _transcribe(self, idx: int, audio: LiveAudio, prev_done: asyncio.Event | None, done: asyncio.Event,
                          started_at: float) -> None:
        s = self.s
        turn: LiveTurn | None = None

        async def current() -> LiveTurn:
            nonlocal turn
            if turn is None:
                if prev_done is not None:
                    try:
                        await asyncio.wait_for(prev_done.wait(), PREV_TURN_S)
                    except TimeoutError:
                        log.warning("session=%s turn %d processed before turn %d finished", s.id, idx, idx - 1)
                turn = LiveTurn(s, self.ctx, list(self.history), idx, "A", self.client)
            return turn

        failed = False
        try:
            try:
                async for seg in _segments(None, audio, load_profile("agent"), self.key, self.gate, label=f"turn {idx}",
                                           turn_started_at=started_at):
                    (await current()).on_segment(seg)
            except SttAuthError as e:
                log.warning("session=%s gnani key rejected: %s", s.id, e)
                s.log.emit("error", {"code": "gnani_key_rejected", "retryable": False, "message_user":
                                     "Your Gnani key was rejected. Check it in Settings. Your report so far is available."})
                self.fatal = True
            except SttError as e:
                failed = True
                log.warning("session=%s turn %d: speech recognition failed (%s)", s.id, idx, e)
            except Exception:  # noqa: BLE001 - one bad turn must not stop the next turn from being processed
                failed = True
                log.exception("session=%s turn %d: unexpected failure", s.id, idx)
            turn = await current()
            if turn.text:
                self.failed_in_a_row = 0
                self.history.append(Turn(speaker="A", text=turn.text))
                self.agent_turns += 1
                if reminder_due(self.agent_turns, self.ctx.answered_by, self.m.reminded):
                    self.m.reminded = True
                    self._reminder(idx)
            elif failed:
                self._speech_gap()
            self.closing.append(asyncio.create_task(self._close(turn, idx, self.closing[-1] if self.closing else None)))
        finally:
            done.set()  # the next turn never waits for a turn that failed

    def _speech_gap(self) -> None:
        self.failed_in_a_row += 1
        self.s.log.emit("banner", {"kind": "stt_gap", "message": "Could not hear one part of the call. Please keep speaking."})
        if self.failed_in_a_row >= MAX_FAILED_TURNS:
            self.s.log.emit("error", {"code": "stt_unavailable", "retryable": True, "message_user":
                                      "The speech service stopped responding, so the call was ended. Your report so far is available."})
            self.fatal = True

    async def _close(self, turn: LiveTurn, idx: int, prev: asyncio.Task | None) -> int:
        score = await turn.finish(await prev if prev else 0)
        self.s.log.emit("turn.ended", {"turn_idx": idx})
        return score

    # ------------------------------------------------------------ coach voice
    async def _sleep_until(self, target) -> None:
        while (left := target() - time.perf_counter()) > 0:
            await asyncio.sleep(left)

    def voice_nudge(self, turn: LiveTurn) -> None:
        """A violation card was shown: speak its coach line in the next pause (called by LiveTurn)."""
        if self.spoken >= MAX_SPOKEN_PER_CALL or turn.idx in self.coaching or turn.nudge is None:
            return
        self.spoken += 1
        self.coaching.add(turn.idx)
        self.coach_tasks.append(asyncio.create_task(self._play(turn.idx, turn.nudge, time.perf_counter())))

    def _reminder(self, idx: int) -> None:
        """Once, at the end of the third agent turn with nobody chosen: the card, and the voice when its clip exists."""
        r = assets.reminder("SELECT")
        if r is None:
            log.warning("session=%s no reminder text for SELECT in the rulebook", self.s.id)
            return
        self.s.log.emit("coach.nudge", {"finding_id": None, "rule_id": "SELECT", "text": r["text"], "audio_url": r["audio_url"],
                                        "latency": {}})
        if not r["audio_url"]:
            log.info("session=%s reminder clip coach/SELECT_1 is missing: card only, no voice", self.s.id)
            return
        self.coach_tasks.append(asyncio.create_task(self._play(idx, r, time.perf_counter())))

    async def _play(self, k: int, line: dict, ready: float) -> None:
        """Speak `line` after turn k, in a pause only: when the visitor is speaking again the voice is skipped (the card stays)."""
        await self.turn_over[k].wait()
        await self._sleep_until(lambda: max(self.ended_at[k] + rules_clock.COACH_AFTER_TURN_S, ready,
                                            self.last_coach_end + rules_clock.COACH_QUEUE_GAP_S))
        if self.cur is not None or self.idx > k:
            log.info("session=%s coach voice skipped for turn %d: the visitor is speaking again", self.s.id, k)
            return
        self.s.log.emit("coach.speak", {"audio_url": line["audio_url"], "duration_ms": line["duration_ms"]})
        self.last_coach_end = time.perf_counter() + line["duration_ms"] / 1000
        self.m.coach_until = self.last_coach_end + COACH_TAIL_S

    # ------------------------------------------------------------ ending
    async def _finish(self, reason: str) -> None:
        s = self.s
        for kind, val in self.splitter.finish():
            self._apply(kind, val)  # commits a turn that is still open
        for task in self.coach_tasks:  # a voice nobody can act on any more
            task.cancel()
        notice = {"limit": "The call reached its time limit.",
                  "no_audio": f"No audio reached the server for {NO_FRAMES_S:.0f} seconds, so the call was ended."}.get(reason)
        if notice:
            s.log.emit("banner", {"kind": reason, "message": notice})
        s.log.emit("stage.status", {"stage": "finishing", "turn_idx": self.idx, "text": "Finishing the checks"})
        try:
            await asyncio.wait_for(self._drain(), FINISH_S)
        except TimeoutError:
            log.warning("session=%s finishing took longer than %.0f s", s.id, FINISH_S)
        s.log.emit("session.ended", {"summary": summary(s)})

    async def _drain(self) -> None:
        await asyncio.gather(*self.turn_tasks, return_exceptions=True)
        await asyncio.gather(*self.closing, return_exceptions=True)
        if self.s.late_tasks:  # late deep answers (up to the 8 s model budget) still update the call
            await asyncio.gather(*self.s.late_tasks, return_exceptions=True)
