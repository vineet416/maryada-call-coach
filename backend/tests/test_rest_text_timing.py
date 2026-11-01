"""Text from the REST fallback is never shown before its turn's audio has ended (replayer clamp and live hold)."""
from app.schedule import plan
from app.session.runner import rest_hold_s

# alternating turns; turn 7 (agent) is long: 7.5 s, like c25 turn 7
DUR = {i: 2000 for i in range(1, 10)}
DUR[7] = 7500
OFF, t = {}, 300
for i in range(1, 10):
    OFF[i] = t
    t += DUR[i] + 1200
TURNS = [{"idx": i, "speaker": "A" if i % 2 else "B", "offset_ms": OFF[i], "duration_ms": DUR[i]} for i in range(1, 10)]


def ev(t, typ, **data):
    return {"seq": 0, "type": typ, "t_ms": t, "data": data}


def recording(path7: str | None, seg_lag7=1400, also_live_first=False):
    """Every turn recorded at its natural start; turn 7's transcript arrives `seg_lag7` after its start (before its audio ends)."""
    out = []
    for i in range(1, 10):
        out.append(ev(OFF[i], "turn.started", turn_idx=i))
        if i == 7:
            continue
        end_lag = DUR[i] + 900  # a live turn: its last segment arrives 0.9 s after the audio ended
        out.append(ev(OFF[i] + end_lag, "transcript.final", turn_idx=i, segment_idx=0, is_last_segment_of_turn=True,
                      **({"stt_path": "realtime"} if path7 else {})))
        out.append(ev(OFF[i] + end_lag + 100, "turn.ended", turn_idx=i))
    extra = {"stt_path": path7} if path7 else {}
    if also_live_first:
        out.append(ev(OFF[7] + 900, "transcript.final", turn_idx=7, segment_idx=0, is_last_segment_of_turn=False, stt_path="realtime"))
        seg_idx = 1
    else:
        seg_idx = 0
    out += [ev(OFF[7] + seg_lag7, "transcript.final", turn_idx=7, segment_idx=seg_idx, is_last_segment_of_turn=True, **extra),
            ev(OFF[7] + seg_lag7 + 5, "finding.pending", turn_idx=7, segment_idx=seg_idx),
            ev(OFF[7] + seg_lag7 + 30, "finding.detected", id="f7", turn_idx=7, rule_id="R6", kind="needs_review"),
            ev(OFF[7] + seg_lag7 + 40, "risk.update", score=10),
            ev(OFF[7] + seg_lag7 + 41, "turn.ended", turn_idx=7)]
    return sorted(out, key=lambda e: e["t_ms"])


def at(p, typ, idx):
    return next(e["t_ms"] for e in p.events if e["type"] == typ and e["data"].get("turn_idx") == idx)


def check_clamped(p):
    end7 = p.starts[7] + DUR[7]
    assert at(p, "transcript.final", 7) == end7  # shown exactly when the audio ends, not 6.1 s earlier
    shift = end7 - (p.starts[7] + 1400)
    assert at(p, "finding.pending", 7) == p.starts[7] + 1405 + shift  # everything derived from that text moves with it
    assert at(p, "finding.detected", 7) == p.starts[7] + 1430 + shift
    assert at(p, "turn.ended", 7) == p.starts[7] + 1441 + shift
    risk = next(e["t_ms"] for e in p.events if e["type"] == "risk.update")
    assert risk == p.starts[7] + 1440 + shift  # the risk update right before the turn's end moves too


def test_marked_rest_text_is_not_shown_before_the_turn_audio_ends():
    check_clamped(plan(recording("rest"), TURNS))


def test_old_recordings_without_a_marker_are_detected_by_the_negative_lag():
    check_clamped(plan(recording(None), TURNS))


def test_a_live_turn_is_not_changed():
    p = plan(recording("rest"), TURNS)
    for i in (1, 3, 5, 9):  # live turns keep their recorded lag after their own start (audio end + 0.9 s)
        assert at(p, "transcript.final", i) == p.starts[i] + DUR[i] + 900
        assert at(p, "turn.ended", i) == p.starts[i] + DUR[i] + 1000


def test_a_live_first_segment_of_a_turn_that_finished_over_rest_is_not_moved():
    p = plan(recording("rest", seg_lag7=3000, also_live_first=True), TURNS)
    firsts = sorted(e["t_ms"] for e in p.events if e["type"] == "transcript.final" and e["data"]["turn_idx"] == 7)
    assert firsts[0] == p.starts[7] + 900  # the live segment keeps its own arrival
    assert firsts[1] == p.starts[7] + DUR[7]  # the REST segment waits for the audio end


def test_a_rest_text_that_already_arrives_after_the_audio_end_is_not_moved():
    p = plan(recording("rest", seg_lag7=DUR[7] + 500), TURNS)
    assert at(p, "transcript.final", 7) == p.starts[7] + DUR[7] + 500


def test_live_hold_is_the_time_left_until_the_audio_ends():
    # c25 turn 7: started at 39.3 s, 7.5 s long, REST text ready at 40.7 s -> hold 6.1 s
    assert abs(rest_hold_s(39.3, 7500, 40.7) - 6.1) < 1e-9
    assert rest_hold_s(39.3, 7500, 47.5) == 0.0  # already past the end: no hold


def test_live_hold_follows_the_call_pace():
    assert abs(rest_hold_s(10.0, 8000, 11.0, pace=0.5) - 3.0) < 1e-9


def test_a_rest_marker_on_a_turn_missing_from_the_manifest_does_not_break_the_replay():
    evs = recording("rest") + [ev(OFF[9] + 500, "turn.started", turn_idx=99),
                               ev(OFF[9] + 900, "transcript.final", turn_idx=99, segment_idx=0, stt_path="rest")]
    plan(sorted(evs, key=lambda e: e["t_ms"]), TURNS)  # must not raise
