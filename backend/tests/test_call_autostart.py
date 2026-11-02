"""A recorded run starts at once from an in-app click; a direct load, a refresh or a pasted link shows the Ready card.
The frontend has no test runner: the pure helper runs under Node (skipped without Node), the page wiring is checked on its source."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"


def text(*parts: str) -> str:
    return SRC.joinpath(*parts).read_text(encoding="utf-8")


# ---- the helper, run for real
@pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")
def test_helper_reads_the_signal_and_the_browser_gesture():
    helper = (SRC / "lib" / "autostart.ts").as_uri()
    script = (
        f"const m = await import({json.dumps(helper)});"
        "const out = {"
        "signal: m.isAutostart(m.AUTOSTART), none: m.isAutostart(null), empty: m.isAutostart({}), other: m.isAutostart({autostart: 'yes'}),"
        "active: m.soundAllowed({userActivation: {hasBeenActive: true}}), idle: m.soundAllowed({userActivation: {hasBeenActive: false}}),"
        "noApi: m.soundAllowed({}), noNavigator: m.soundAllowed(undefined)};"
        "console.log(JSON.stringify(out));"
    )
    run = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60, check=True)
    assert json.loads(run.stdout.strip().splitlines()[-1]) == {
        "signal": True, "none": False, "empty": False, "other": False,
        "active": True, "idle": False, "noApi": False, "noNavigator": False}


# ---- autostart from Home and from Run again
def test_home_calls_and_run_again_pass_the_signal_and_unlock_sound_in_the_click():
    cases = text("pages", "Cases.tsx")
    links = re.findall(r"<Link to=\{`/call/\$\{c\.id\}`\}.*?className=", cases)
    assert len(links) == 2  # the featured call and every call card in the sample list
    for tag in links:
        assert "state={AUTOSTART}" in tag and "onClick={() => audio.unlock()}" in tag
    report = text("pages", "CallReport.tsx")
    run_again = re.search(r"<Link to=\{`/call/\$\{scenario\.id\}`\}[^\n]*>Run again</Link>", report)
    assert run_again and "state={AUTOSTART}" in run_again.group(0) and "onClick={() => audio.unlock()}" in run_again.group(0)


def test_call_page_uses_the_signal_once_and_removes_it():
    s = text("pages", "LiveCall.tsx")
    assert "isAutostart(location.state)" in s
    assert "navigate(`${location.pathname}${location.search}`, { replace: true, state: null })" in s  # refresh and Back see no signal
    assert "autoDone" in s  # one use per page load


def test_call_page_starts_a_recorded_run_only_when_sound_is_allowed():
    s = text("pages", "LiveCall.tsx")
    gate = re.search(r"if \(scenario\.has_replay && soundAllowed\(\)\) \{(.*?)\n    \}", s, re.DOTALL)
    assert gate and "begin('replay')" in gate.group(1)
    assert s.count("begin('replay')") >= 2  # the other calls are the existing fallback buttons, not the autostart
    assert not re.search(r"soundAllowed\(\)[^\n]*\n[^\n]*begin\('live'", s)


def test_ready_card_stays_for_a_direct_load_and_is_hidden_only_while_autostarting():
    s = text("pages", "LiveCall.tsx")
    assert "Press start to allow sound" in s and "<StartCard" in s  # the fallback
    assert "const starting = (autostart && phase === 'ready') || (auto && (phase === 'ready' || phase === 'starting'))" in s
    assert "if (phase === 'loading' || !scenario || starting)" in s


def test_autostart_never_reaches_the_direct_routes():
    app = text("App.tsx")
    assert "AUTOSTART" not in app  # only in-app links carry the signal
    helper = text("lib", "autostart.ts")
    assert "hasBeenActive === true" in helper and "AUTOSTART = { autostart: true }" in helper
