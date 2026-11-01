"""The recorded runs shipped in data/replay play correctly on the call clock (headless: no server, no audio)."""
import itertools
import json

import pytest
from app.config import settings
from app.schedule import plan
from app.session import assets

FILES = sorted(p for p in (settings.data_dir / "replay").glob("c*.json"))
HERO_RISK_PATH = [0, 0, 0, 65, 55, 45]


def load(p):
    d = json.loads(p.read_text(encoding="utf-8"))
    turns = assets.audio_manifest()[d["scenario_id"]]["turns"]
    return d, turns, plan(d["events"], turns)


def test_there_are_recorded_runs():
    assert {"c06", "c01", "c30", "c17", "c25"} <= {p.stem for p in FILES}


@pytest.mark.parametrize("p", FILES, ids=lambda p: p.stem)
def test_recording_plays_on_the_call_clock(p):
    d, turns, pl = load(p)
    assert d["scenario_id"] == p.stem
    ev = pl.events
    assert [e["seq"] for e in ev] == list(range(1, len(ev) + 1))
    assert all(a["t_ms"] <= b["t_ms"] for a, b in itertools.pairwise(ev))
    assert ev[0]["type"] == "session.started" and ev[-1]["type"] == "session.ended"
    order = [t["idx"] for t in turns]
    started = [e["data"]["turn_idx"] for e in ev if e["type"] == "turn.started"]
    assert started == order  # every turn of the call starts, in order
    dur = {t["idx"]: t["duration_ms"] for t in turns}
    gaps = [pl.starts[b] - pl.starts[a] - dur[a] for a, b in itertools.pairwise(order)]
    assert min(gaps) >= 900 - 5  # the audio of two turns never overlaps (heard gap at least 0.9 s)


@pytest.mark.parametrize("p", FILES, ids=lambda p: p.stem)
def test_no_turn_shows_its_final_text_before_its_audio_has_ended(p):
    _, turns, pl = load(p)
    for t in turns:
        segs = [e for e in pl.events if e["type"] == "transcript.final" and e["data"]["turn_idx"] == t["idx"]]
        assert segs, f"turn {t['idx']} has no transcript"
        last = max(segs, key=lambda e: e["data"]["segment_idx"])
        assert last["t_ms"] >= pl.starts[t["idx"]] + t["duration_ms"], f"turn {t['idx']} text appears before its audio ends"


@pytest.mark.parametrize("p", FILES, ids=lambda p: p.stem)
def test_a_coach_clip_ends_before_the_next_agent_turn_starts(p):
    _, turns, pl = load(p)
    who = {t["idx"]: t["speaker"] for t in turns}
    speaks = [e for e in pl.events if e["type"] == "coach.speak"]
    for e in speaks:
        end = e["t_ms"] + e["data"]["duration_ms"]
        later = [pl.starts[i] for i in pl.starts if who[i] == "A" and pl.starts[i] > e["t_ms"]]
        if later:
            assert end <= min(later)  # the clip is over before the agent speaks again
    assert pl.agent_started_anyway == 0  # no shipped run has an agent that started without its nudge ready


def test_the_hero_and_c17_have_spoken_coach_clips():
    for name, n in (("c06", 1), ("c17", 2)):
        _, _, pl = load(settings.data_dir / "replay" / f"{name}.json")
        assert sum(1 for e in pl.events if e["type"] == "coach.speak") == n


def test_c25_turn_7_rest_text_is_shown_at_the_audio_end_not_earlier():
    p = settings.data_dir / "replay" / "c25.json"
    _, turns, pl = load(p)
    t7 = next(t for t in turns if t["idx"] == 7)
    text = [e for e in pl.events if e["type"] == "transcript.final" and e["data"]["turn_idx"] == 7]
    assert min(e["t_ms"] for e in text) == pl.starts[7] + t7["duration_ms"]  # recorded 6.1 s earlier
    found = [e["t_ms"] for e in pl.events if e["type"] == "finding.detected" and e["data"]["turn_idx"] == 7 and e["data"]["rule_id"] == "R6"]
    assert found and min(found) >= pl.starts[7] + t7["duration_ms"]


def test_the_hero_is_the_approved_run():
    d = json.loads((settings.data_dir / "replay" / "c06.json").read_text(encoding="utf-8"))
    ev = d["events"]
    assert [e["data"]["score"] for e in ev if e["type"] == "risk.update"] == HERO_RISK_PATH
    rules = {e["data"]["rule_id"] for e in ev if e["type"] == "finding.detected" and e["data"]["kind"] != "good_practice"}
    assert rules == {"R3", "R5"}  # a threat, and no false R2
    assert sum(1 for e in ev if e["type"] == "coach.speak") == 1
