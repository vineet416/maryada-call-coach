"""docs/EVAL-NOTES.md carries the numbers the Evaluation page no longer shows (checked against the saved data), and the coach volume setting."""
import json
import re
import subprocess
from pathlib import Path

from app import evaluation
from app.api import rest
from app.session import assets

ROOT = Path(__file__).resolve().parents[2]
NOTES = (ROOT / "docs" / "EVAL-NOTES.md").read_text(encoding="utf-8")
SRC = ROOT / "frontend" / "src"


def test_notes_are_tracked_and_not_ignored():
    assert subprocess.run(["git", "check-ignore", "-q", "docs/EVAL-NOTES.md"], cwd=ROOT, check=False).returncode == 1
    assert subprocess.run(["git", "ls-files", "--error-unmatch", "docs/EVAL-NOTES.md"], cwd=ROOT, capture_output=True, check=False).returncode == 0


def test_notes_numbers_match_the_saved_data():
    p = evaluation.eval_payload()
    res, rev = p["results"], p["review"]
    run = res["full"]["clean"]
    s = run["all"]["overall"]["strict"]
    a = rev["adjusted"]["full/clean"]["all"]["strict"]
    verdicts = [i["verdict"] for i in rev["items"]]
    change = json.loads((ROOT / "data/eval/engine_changes.json").read_text(encoding="utf-8"))["changes"][0]
    label = res["label_changes"][0]
    ex = {(e["call"], e["turn"]): e for e in run["examples"]}
    expected = [
        f"{res['n_calls']} calls, {s['tp'] + s['fn']} labelled units, one run per condition",
        f"{res['model_info']['thresholds']['violation']} for a violation, {res['model_info']['thresholds']['needs_review']} for needs review",
        f"{verdicts.count('real')} real, {verdicts.count('unsure')} unsure, {verdicts.count('not_a_violation')} not a violation",
        f"{a['precision_low']:.3f} to {a['precision_high']:.3f}",
        f"Recall is unchanged: {a['recall']:.3f}",
        f"{len(rev['items'])} extra flags",
        f"`{label['label_hash_before']}`", f"`{label['label_hash_after']}`", f"`{res['labels_hash']}`",
        res["model_info"]["llm"], res["model_info"]["stt"],
        f"confidence {ex[('c08', 11)]['detection']['confidence']:.2f}", f"confidence {ex[('c11', 11)]['detection']['confidence']:.2f}",
        ex[("c08", 11)]["text"], ex[("c11", 11)]["text"],
        f"It removed {len(change['removed_flags'])} flags",
        f"{change['before']['with_review']['fp']} / {change['before']['with_review']['fn']}",
        f"{change['after']['with_review']['tp']} / {change['after']['with_review']['fp']} / {change['after']['with_review']['fn']}",
    ]
    for text in expected:
        assert text in NOTES, text
    assert "tools/run_eval.py --report" in NOTES


# ---- coach voice volume
def test_rules_endpoint_gives_an_existing_coach_clip_for_the_sample_button():
    rules = rest.list_rules()
    clips = [r["coach_clip"] for r in rules if r.get("coach_clip")]
    assert clips, "the sample button needs at least one coach clip"
    for url in clips:
        assert (assets.audio_dir() / url.removeprefix("/audio/")).is_file(), url


def test_volume_default_is_todays_level_and_the_range_is_zero_to_one_hundred():
    engine = (SRC / "lib" / "audioEngine.ts").read_text(encoding="utf-8")
    assert "export const COACH_GAIN = 0.84" in engine and "export const DUCK_DB = -1.5" in engine  # the quiet mix is unchanged
    assert "DEFAULT_COACH_VOLUME = Math.round(COACH_GAIN * 100)" in engine
    assert "Math.min(100, Math.max(0," in engine
    assert "this.coachVolume / 100" in engine  # element volume: 100 is the clip at its own level, which does not clip
    assert re.search(r"try \{[^}]*localStorage\.getItem\(VOLUME_KEY\)", engine, re.DOTALL) and "localStorage.setItem(VOLUME_KEY" in engine


def test_settings_slider_is_labelled_keyboard_operable_and_off_with_the_voice():
    s = (SRC / "pages" / "Settings.tsx").read_text(encoding="utf-8")
    assert 'htmlFor="coach-volume"' in s and "Coach voice volume" in s and 'type="range"' in s
    assert "min={0}" in s and "max={100}" in s and "disabled={!voice}" in s and "Play sample" in s
