"""The replayer files every event under its OWN turn, even when it arrived during a later turn (slow transcript)."""
from app.schedule import plan

# 11 alternating turns, odd = agent; 2 s each, natural start every 3 s
TURNS = [{"idx": i, "speaker": "A" if i % 2 else "B", "offset_ms": (i - 1) * 3000, "duration_ms": 2000} for i in range(1, 12)]
NAT = {t["idx"]: t["offset_ms"] for t in TURNS}


def ev(t, typ, **data):
    return {"seq": 0, "type": typ, "t_ms": t, "data": data}


def base_events():
    out = []
    for i in range(1, 12):
        out.append(ev(NAT[i], "turn.started", turn_idx=i))
        if i != 7:
            out.append(ev(NAT[i] + 2300, "turn.ended", turn_idx=i))
    return out


def with_nudge(nudge_t):
    """Turn 7 (agent) is flagged; the finding and the nudge arrive at call time `nudge_t` (recorded), whichever turn is then current."""
    evs = base_events()
    evs += [ev(nudge_t, "finding.detected", id="f7", turn_idx=7, rule_id="R3", kind="violation"),
            ev(nudge_t + 10, "coach.nudge", finding_id="f7", rule_id="R3"),
            ev(nudge_t + 2000, "coach.speak", duration_ms=4000),
            ev(nudge_t + 30, "turn.ended", turn_idx=7)]
    return sorted(evs, key=lambda e: e["t_ms"])


def test_a_late_nudge_for_turn_7_stays_on_turn_7_not_8_or_9():
    p = plan(with_nudge(NAT[8] + 1500), TURNS)  # arrives while turn 8 (the borrower) is playing
    assert list(p.coach) == [7]
    assert p.coach[7] == p.starts[8] + 3500  # 3.5 s after the NEXT speaker starts
    assert p.starts[8] == NAT[8]  # the borrower is not moved by the nudge
    assert p.agent_started_anyway == 0
    assert p.starts[9] == p.coach[7] + 4000 + 1000  # the agent follows the clip by 1 s


def test_a_nudge_that_arrives_during_turn_9_is_still_turn_7s_and_the_2s_wait_applies_to_turn_9():
    p = plan(with_nudge(NAT[9] + 6000), TURNS)  # ready 30 s after turn 7 started... far past turn 9's natural start
    assert list(p.coach) == [7]
    assert p.starts[8] == NAT[8]
    assert p.starts[9] == NAT[9] + 2000  # waited the 2 s cap, then started without the nudge
    assert p.agent_started_anyway == 1
    assert p.starts[11] == NAT[11] + 2000  # later agent turns are not held for turn 7's nudge again


def test_without_a_nudge_the_wait_for_the_previous_agent_turn_uses_its_own_turn_ended():
    evs = base_events()
    evs.append(ev(NAT[9] + 1000, "turn.ended", turn_idx=7))  # turn 7 settles late, while turn 9 is playing in the recording
    p = plan(sorted(evs, key=lambda e: e["t_ms"]), TURNS)
    assert p.starts[9] == NAT[7] + (NAT[9] + 1000 - NAT[7])  # = turn 7's start + its recorded settle lag
    assert p.starts[9] <= NAT[9] + 2000


def test_every_event_moves_with_its_own_turn():
    evs = base_events() + [ev(NAT[8] + 500, "transcript.final", turn_idx=7, segment_idx=3, text="x", tokens=[])]
    p = plan(sorted(evs, key=lambda e: e["t_ms"]), TURNS)
    late = next(e for e in p.events if e["type"] == "transcript.final")
    assert late["t_ms"] == p.starts[7] + (NAT[8] + 500 - NAT[7])  # same offset from ITS turn's start
