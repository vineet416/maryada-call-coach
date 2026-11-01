"""Replay recorder and player. The recorded envelope stream is the demo's source of truth."""
import asyncio
import copy
import json
from collections.abc import Callable
from pathlib import Path

from .config import settings


def replay_path(scenario_id: str) -> Path:
    return settings.data_dir / "replay" / f"{scenario_id}.json"


def save(scenario_id: str, events: list[dict]) -> Path:
    p = replay_path(scenario_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"scenario_id": scenario_id, "events": events}, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def load(scenario_id: str) -> list[dict] | None:
    p = replay_path(scenario_id)
    return json.loads(p.read_text(encoding="utf-8"))["events"] if p.exists() else None


def as_replay(events: list[dict]) -> list[dict]:
    """Same stream; only the two labels that say where it came from change."""
    out = copy.deepcopy(events)
    for e in out:
        if e["type"] == "session.started":
            e["data"]["effective_mode"] = "replay"
        elif e["type"] == "transcript.final":
            e["data"]["source"] = "replay"
    return out


def remaining(events: list[dict], after_turn: int) -> list[dict]:
    """Recorded events from the first turn after `after_turn` to the end, times rebased to zero."""
    start = next((i for i, e in enumerate(events) if e["type"] == "turn.started" and e["data"]["turn_idx"] > after_turn),
                 len(events))
    rest = copy.deepcopy(events[start:])
    base = rest[0]["t_ms"] if rest else 0
    for e in rest:
        e["t_ms"] -= base
    return rest


def schedule(events: list[dict]) -> list[tuple[float, dict]]:
    """(delay in seconds since the previous event, event), from the recorded t_ms."""
    prev, res = 0, []
    for e in events:
        res.append((max(0, e["t_ms"] - prev) / 1000, e))
        prev = e["t_ms"]
    return res


COACH_GAP_MS = 300  # the pause after a coach clip when the call is held for it


def retime(events: list[dict], turn_starts: dict[int, int], hold: bool = False) -> list[dict]:
    """Put a recording on the natural call clock. A turn starts at its audio offset (`turn_starts`, ms), and every
    event keeps its recorded lag after its own turn's start, so the transcript and checks arrive as late as they did
    in the recorded run while the call audio never waits for them. With `hold` the call pauses while a coach clip
    plays: everything after the clip moves later by its length. Envelopes are re-sequenced in time order."""
    out: list[dict] = []
    rec_start = nat_start = 0
    in_turn = False
    for e in copy.deepcopy(events):
        if e["type"] == "turn.started":
            idx = e["data"]["turn_idx"]
            rec_start, nat_start, in_turn = e["t_ms"], turn_starts.get(idx, e["t_ms"]), True
        e["t_ms"] = nat_start + e["t_ms"] - rec_start if in_turn else e["t_ms"]
        out.append(e)
    out.sort(key=lambda e: e["t_ms"])  # stable: equal times keep the recorded order
    if hold:  # in call time order: everything after a coach clip moves later by the clip's length
        shift = 0
        for e in out:
            e["t_ms"] += shift
            if e["type"] == "coach.speak":
                shift += e["data"].get("duration_ms", 0) + COACH_GAP_MS
    for n, e in enumerate(out, 1):
        e["seq"] = n
    return out


async def play(events: list[dict], emit: Callable[[dict], None], pace: float | None = None,
               turn_starts: dict[int, int] | None = None, hold: bool = False) -> None:
    """Re-emit the recorded envelopes on the natural call clock (see retime), scaled by PACE."""
    pace = settings.pace if pace is None else pace
    events = as_replay(events)
    if turn_starts is not None:
        events = retime(events, turn_starts, hold)
    loop = asyncio.get_running_loop()
    t0, due = loop.time(), 0.0
    for delay, e in schedule(events):
        due += delay * pace  # against the start, so sleeps never add up to drift
        if (wait := t0 + due - loop.time()) > 0:
            await asyncio.sleep(wait)
        emit(e)
