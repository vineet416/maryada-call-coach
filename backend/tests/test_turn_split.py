"""Speak live: the TurnSplitter cuts an 8 kHz PCM16 stream into turns (pure, time is counted from the audio)."""
from app.session.turn_split import MAX_TURN_S, PAUSE_S, TurnSplitter

FRAME = 1024  # 64 ms
LOUD = b"\xb8\x0b\x48\xf4" * (FRAME // 4)  # +3000 / -3000 square wave
QUIET = bytes(FRAME)


def run(splitter, frames):
    return [o for f in frames for o in splitter.feed(f)]


def kinds(outs):
    return [k for k, _ in outs if k != "audio"]


def frames_for(seconds):
    return int(seconds * 1000 / 64) + 1


def test_silence_makes_no_turn():
    assert kinds(run(TurnSplitter(), [QUIET] * 100)) == []


def test_speech_then_pause_is_one_turn():
    outs = run(TurnSplitter(), [QUIET] * 5 + [LOUD] * 16 + [QUIET] * frames_for(PAUSE_S) + [QUIET] * 5)
    assert kinds(outs) == ["start", ("end")]
    assert [v for k, v in outs if k == "end"] == ["pause"]


def test_short_pause_stays_in_the_turn():
    outs = run(TurnSplitter(), [LOUD] * 10 + [QUIET] * 10 + [LOUD] * 10)  # 0.64 s gap
    assert kinds(outs) == ["start"]


def test_two_turns_when_the_pause_is_long():
    gap = [QUIET] * frames_for(PAUSE_S)
    assert kinds(run(TurnSplitter(), [LOUD] * 10 + gap + [LOUD] * 10 + gap)) == ["start", "end", "start", "end"]


def test_first_word_is_kept_by_the_preroll():
    s = TurnSplitter()
    outs = run(s, [QUIET] * 20 + [LOUD] * 8)
    audio = [v for k, v in outs if k == "audio"]
    assert audio[0] == QUIET  # quiet lead-in kept
    assert sum(len(a) for a in audio) <= (300 + 8 * 64) * 16 + FRAME  # lead-in is at most the preroll


def test_cough_shorter_than_the_start_time_is_ignored():
    assert kinds(run(TurnSplitter(), [QUIET] * 5 + [LOUD] * 2 + [QUIET] * 40)) == []


def test_long_speech_is_cut_at_the_cap_and_continues():
    outs = run(TurnSplitter(), [LOUD] * frames_for(MAX_TURN_S * 2 + 2))
    assert kinds(outs)[:4] == ["start", "end", "start", "end"]
    assert next(v for k, v in outs if k == "end") == "cap"


def test_finish_closes_an_open_turn_once():
    s = TurnSplitter()
    run(s, [LOUD] * 10)
    assert s.finish() == [("end", "finish")]
    assert s.finish() == []


def test_noise_floor_adapts_to_a_steady_hum():
    hum = b"\x40\x00\xc0\xff" * (FRAME // 4)  # amplitude 64, below the absolute minimum
    assert kinds(run(TurnSplitter(), [hum] * 200)) == []
