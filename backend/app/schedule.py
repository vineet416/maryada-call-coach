"""Call timing rules shared by the live clock and the replayer (decided 2026-11-01).

The audio of a call is stitched with natural gaps (the turn offsets in the audio manifest). A coach nudge changes the clock in
two ways, and only then: the coach clip starts COACH_AFTER_TURN_S after the nudged agent turn ends, or when the card is shown if
that is later (decided 2026-11-02), and the agent's next turn starts AGENT_AFTER_COACH_S after the clip ends. A clip that would begin
after the agent's next turn has already started is skipped (the card stays). The call audio itself never pauses:
the agent simply starts later (or a little earlier than the natural schedule, never before the usual minimum gap).
"""
import copy
import logging
from dataclasses import dataclass, field

COACH_AFTER_TURN_S = 0.5  # the coach clip starts this long after the nudged agent turn ends (or when the card is shown, if later)
AGENT_AFTER_COACH_S = 1.0  # the agent's next turn starts this long after the coach clip ends
AGENT_WAIT_S = 2.0  # the agent waits at most this long (past its natural start) for a nudge that is not ready yet
COACH_QUEUE_GAP_S = 1.0  # two coach clips never run closer than this
MIN_FILE_GAP_S = 0.9  # smallest silence between two clips: the heard gap of 1.0 s minus the 50 ms kept at each clip edge
COACH_HOLD_GAP_MS = 300  # the pause option: the call also waits this long after the clip

log = logging.getLogger("maryada.schedule")


@dataclass
class Plan:
    events: list[dict]
    agent_started_anyway: int = 0  # times the agent started after the 2 s wait without the nudge being ready
    coach: dict[int, int] = field(default_factory=dict)  # nudged turn -> coach clip start (ms)
    starts: dict[int, int] = field(default_factory=dict)  # turn -> start (ms)
    skipped: list[int] = field(default_factory=list)  # nudged turns whose voice was dropped: the next agent turn had already started


def rest_text_lags(evs: list[dict], dur: dict[int, int]) -> dict[int, int]:
    """Turns whose transcript came from the REST fallback -> recorded lag (ms after the turn's start) of the first REST segment.
    New recordings mark such a segment (data.stt_path == "rest"); a segment from a retried realtime socket
    (stt_path == "realtime_retry") is live but follows the same never-before-its-audio rule. Older recordings carry no marker: there a turn whose LAST
    segment arrived before the turn's audio ended is a REST turn (live text cannot arrive before the speech it transcribes is over:
    connect time plus the vendor delay put it at least 0.3 s after the end). Needs the events' _idx and _lag."""
    out: dict[int, int] = {}
    segs: dict[int, list[dict]] = {}
    for e in evs:
        if e["type"] == "transcript.final" and e.get("_idx") is not None:
            segs.setdefault(e["_idx"], []).append(e)
    for k, sg in segs.items():
        marked = [e["_lag"] for e in sg if e["data"].get("stt_path") == "rest"]
        if marked:
            out[k] = min(marked)
            continue
        last = max(sg, key=lambda e: e["data"].get("segment_idx", 0))
        path = last["data"].get("stt_path")
        # a retried socket's segment was live, but it is held the same way: never shown before the audio it covers has ended
        old_style = path is None and not any("stt_path" in e["data"] for e in sg)
        if (path == "realtime_retry" or old_style) and k in dur and last["_lag"] < dur[k]:
            out[k] = last["_lag"]
    return out


def plan(events: list[dict], turns: list[dict], hold: bool = False) -> Plan:
    """Put a recorded event stream on the call clock. `turns` is the manifest list (idx, speaker, offset_ms, duration_ms).
    Every event keeps its recorded lag after its own turn's start, so transcript and checks arrive as late as they did
    in the recorded run; turn starts follow the rules above. With `hold` (the user's pause option) there is no agent wait:
    everything after a coach clip simply moves later by the clip's length."""
    evs = copy.deepcopy(events)
    order = [t["idx"] for t in turns]
    nat = {t["idx"]: t["offset_ms"] for t in turns}
    dur = {t["idx"]: t["duration_ms"] for t in turns}
    who = {t["idx"]: t["speaker"] for t in turns}

    # Every event is filed under ITS OWN turn (data.turn_idx; a nudge: the turn of its finding; a coach clip: its nudge; a risk
    # update: the turn that ends right after it), not under the turn that happened to be current when it arrived: with a slow
    # transcript an event can arrive during a later turn.
    rec_start = {e["data"]["turn_idx"]: e["t_ms"] for e in evs if e["type"] == "turn.started"}
    finding_turn = {e["data"]["id"]: e["data"]["turn_idx"] for e in evs if e["type"] == "finding.detected" and "id" in e["data"]}
    cur = None
    pending: int | None = None
    for n, e in enumerate(evs):
        d = e["data"]
        if e["type"] == "turn.started":
            cur = d["turn_idx"]
        own = d.get("turn_idx") if isinstance(d, dict) else None
        if e["type"] == "coach.nudge":
            own = finding_turn.get(d.get("finding_id"), cur)
        elif e["type"] == "coach.speak":
            own = pending if pending is not None else cur
        elif e["type"] == "risk.update" and n + 1 < len(evs) and evs[n + 1]["type"] == "turn.ended":
            own = evs[n + 1]["data"]["turn_idx"]
        elif own is None:
            own = cur
        if own not in rec_start:  # before the first turn, or a stage label without a turn: keep the recorded time
            own = None
        e["_idx"], e["_lag"] = own, (e["t_ms"] - rec_start[own] if own is not None else 0)
        if e["type"] == "coach.nudge" and own is not None:
            pending = own
        elif e["type"] == "coach.speak":
            pending = None

    # Text that came from the REST fallback is never shown before its turn's audio has ended (the live runner holds it the same
    # way). The first REST segment and everything derived from it (checks, findings, nudge, turn end, risk) move later together.
    for k, lag0 in rest_text_lags(evs, dur).items():
        shift = dur.get(k, 0) - lag0
        if shift > 0:
            for e in evs:
                if e["_idx"] == k and e["_lag"] >= lag0:
                    e["_lag"] += shift

    nudges: dict[int, dict] = {}  # turn -> {lag, speak: event}
    ended_lag: dict[int, int] = {}
    pending = None
    for e in evs:
        own = e["_idx"]
        if e["type"] == "turn.ended" and own is not None:
            ended_lag[own] = e["_lag"]
        if e["type"] == "coach.nudge" and own is not None:
            pending = own
            nudges.setdefault(own, {"lag": e["_lag"], "speak": None})
        elif e["type"] == "coach.speak" and pending is not None:
            nudges[pending]["speak"] = e
            pending = None
    nudges = {k: v for k, v in nudges.items() if v["speak"] is not None and k in nat}

    start: dict[int, int] = {}
    coach: dict[int, int] = {}
    skipped: list[int] = []
    last_coach_end = -10**9
    late = 0

    def coach_start(k: int) -> int | None:
        """When the clip of nudged turn k starts, or None when it is skipped (the agent's next turn had already started)."""
        nonlocal last_coach_end
        if k not in coach and k not in skipped:
            i = order.index(k)
            card = start[k] + nudges[k]["lag"]
            at = max(start[k] + dur[k] + round(COACH_AFTER_TURN_S * 1000), card, last_coach_end + round(COACH_QUEUE_GAP_S * 1000))
            nxt_agent = next((j for j in order[i + 1:] if who[j] == "A"), None)
            if nxt_agent is not None and nxt_agent in start and start[nxt_agent] <= at:
                skipped.append(k)
                log.info("coach voice skipped for turn %s: it would start at %d ms, after the next agent turn began (%d ms)",
                         k, at, start[nxt_agent])
            else:
                coach[k] = at
                last_coach_end = at + nudges[k]["speak"]["data"].get("duration_ms", 0)
        return coach.get(k)

    shift = 0
    for pos, idx in enumerate(order):
        s = nat[idx] + shift
        if not hold and who[idx] == "A":
            prev_agents = [j for j in order[:pos] if who[j] == "A"]
            k = prev_agents[-1] if prev_agents else None
            if k is not None and k in nudges:
                ready = start[k] + nudges[k]["lag"]
                if ready > s + round(AGENT_WAIT_S * 1000):  # not ready in time: start anyway, the clip plays when ready
                    s += round(AGENT_WAIT_S * 1000)
                    late += 1
                    start[idx] = s  # this agent turn begins now: a clip that is only ready later is stale
                    coach_start(k)
                else:
                    c_end = coach_start(k) + nudges[k]["speak"]["data"].get("duration_ms", 0)
                    after = order[order.index(k) + 1]
                    floor = start[after] + dur[after] + round(MIN_FILE_GAP_S * 1000) if after != idx else 0
                    s = max(s, c_end + round(AGENT_AFTER_COACH_S * 1000), floor)  # an early clip never pulls the agent ahead of the call schedule
            elif k is not None and k in ended_lag:  # no spoken nudge: wait for its check to settle, at most 2 s
                s = max(s, min(start[k] + ended_lag[k], s + round(AGENT_WAIT_S * 1000)))
            shift = s - nat[idx]
        start[idx] = s
    for k in nudges:
        coach_start(k)

    for e in evs:
        idx = e.pop("_idx")
        lag = e.pop("_lag")
        e["t_ms"] = start[idx] + lag if idx is not None and idx in start else e["t_ms"]
    for k, n in nudges.items():
        if k in coach:
            n["speak"]["t_ms"] = coach[k]
    gone = {id(nudges[k]["speak"]) for k in skipped}
    evs = [e for e in evs if id(e) not in gone]  # a skipped voice: the card stays, the clip is not played
    evs.sort(key=lambda e: e["t_ms"])  # stable: equal times keep the recorded order
    if hold:  # in call time order: everything after a coach clip moves later by the clip's length
        moved = 0
        for e in evs:
            e["t_ms"] += moved
            if e["type"] == "coach.speak":
                moved += e["data"].get("duration_ms", 0) + COACH_HOLD_GAP_MS
    for n, e in enumerate(evs, 1):
        e["seq"] = n
    return Plan(evs, late, coach, start, skipped)
