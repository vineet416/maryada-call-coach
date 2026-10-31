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


def schedule(events: list[dict]) -> list[tuple[float, dict]]:
    """(delay in seconds since the previous event, event), from the recorded t_ms."""
    prev, res = 0, []
    for e in events:
        res.append((max(0, e["t_ms"] - prev) / 1000, e))
        prev = e["t_ms"]
    return res


async def play(events: list[dict], emit: Callable[[dict], None], pace: float | None = None) -> None:
    """Re-emit the recorded envelopes with their original relative timing (scaled by PACE)."""
    pace = settings.pace if pace is None else pace
    for delay, e in schedule(as_replay(events)):
        await asyncio.sleep(delay * pace)
        emit(e)
