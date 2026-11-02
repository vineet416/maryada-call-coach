"""Speak live: the TurnSplitter cuts an 8 kHz PCM16 stream into turns (pure, time is counted from the audio)."""
import struct

import pytest

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
    assert kinds(run(TurnSplitter(), [QUIET] * 12 + [LOUD] * 10 + gap + [LOUD] * 10 + gap)) == ["start", "end", "start", "end"]


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
    run(s, [QUIET] * 12 + [LOUD] * 10)
    assert s.finish() == [("end", "finish")]
    assert s.finish() == []


def test_noise_floor_adapts_to_a_steady_hum():
    hum = b"\x40\x00\xc0\xff" * (FRAME // 4)  # amplitude 64, below the absolute minimum
    assert kinds(run(TurnSplitter(), [hum] * 200)) == []


def tone(amplitude):
    """A steady square-wave frame: its RMS is the amplitude."""
    return struct.pack("<2h", amplitude, -amplitude) * (FRAME // 4)


def call(ambient, gap_s, pause_s=PAUSE_S, sentences=5):
    """The ambient hum, then `sentences` spoken sentences of 2 s with `gap_s` of hum between them."""
    frames = [tone(ambient)] * 8
    for i in range(sentences):
        frames += [tone(3000)] * frames_for(2.0)
        frames += [tone(ambient)] * frames_for(gap_s if i < sentences - 1 else 2.0)
    return run(TurnSplitter(pause_s=pause_s), frames)


@pytest.mark.parametrize("ambient", [60, 280, 350, 600, 900])
def test_a_steady_hum_above_the_old_threshold_does_not_glue_the_call_into_one_turn(ambient):
    # before the floor followed loud-looking frames, a hum above 300 RMS never read as quiet: no turn ever ended
    assert kinds(call(ambient, gap_s=1.6)) == ["start", "end"] * 5


def test_sentences_with_pauses_under_the_limit_are_one_turn():
    assert kinds(call(60, gap_s=0.9)) == ["start", "end"]  # five sentences, one turn: no third-turn reminder can follow


def test_a_shorter_pause_limit_splits_the_same_speech_into_turns():
    assert kinds(call(60, gap_s=0.9, pause_s=0.8)) == ["start", "end"] * 5


def test_the_last_turn_reports_its_speech_and_its_longest_quiet():
    s = TurnSplitter()
    run(s, [LOUD] * 16 + [QUIET] * 8 + [LOUD] * 16 + [QUIET] * frames_for(PAUSE_S))
    assert 2400 <= s.last_turn["speech_ms"] <= 2700 and 480 <= s.last_turn["longest_quiet_ms"] <= 1300


def natural(level, seconds):
    """Speech as it is: a short dip to the room level every half second or so."""
    frames = []
    while len(frames) < frames_for(seconds):
        frames += [tone(level)] * 7 + [tone(60)] * 2
    return frames


@pytest.mark.parametrize("level", [700, 1000, 1500, 3000])
def test_speech_from_the_very_first_frame_starts_a_turn_and_the_next_one_too(level):
    gap = [QUIET] * frames_for(PAUSE_S)
    assert kinds(run(TurnSplitter(), natural(level, 2.0) + gap + natural(level, 2.0) + gap)) == ["start", "end", "start", "end"]


def test_the_first_words_are_kept_when_the_call_opens_with_speech():
    outs = run(TurnSplitter(), natural(1500, 2.0) + [QUIET] * frames_for(PAUSE_S))
    sent = sum(len(v) for k, v in outs if k == "audio")
    assert sent >= (2000 + 1200 - 150) * 16  # the whole speech and the closing pause: nothing from the first frames was dropped


def test_soft_speech_in_a_noisy_room_is_not_cut_mid_sentence():
    ambient, soft = tone(400), tone(1800)  # speech about 13 dB over the hum, with short dips to the hum inside each sentence
    sentence = ([soft] * 12 + [ambient] * 4) * 4
    outs = run(TurnSplitter(), [ambient] * 20 + sentence + [ambient] * frames_for(PAUSE_S))
    assert kinds(outs) == ["start", "end"]


def test_a_hum_that_starts_the_call_as_a_turn_is_learned_and_the_turn_ends():
    hum = tone(480)  # just over the threshold of the first frames
    outs = run(TurnSplitter(), [hum] * frames_for(10) + [tone(3000)] * frames_for(2.0) + [hum] * frames_for(3.0))
    ends = [v for k, v in outs if k == "end"]
    assert ends and ends[0] == "pause"  # the hum no longer glues the call into one 25 s turn
    assert kinds(outs).count("start") >= 1


def test_the_floor_after_a_turn_is_the_room_it_learned_not_the_window_before_it():
    s = TurnSplitter()
    run(s, [tone(60)] * 40 + [tone(3000)] * 20 + [tone(60)] * frames_for(PAUSE_S))
    assert s.floor < 150 and not s.in_turn


def test_longest_quiet_is_a_pause_inside_the_turn_not_the_closing_one():
    s = TurnSplitter()
    run(s, [LOUD] * 16 + [QUIET] * 8 + [LOUD] * 16 + [QUIET] * frames_for(PAUSE_S))
    assert 480 <= s.last_turn["longest_quiet_ms"] <= 560  # the 8-frame gap (512 ms), not the 1.2 s that ended the turn
