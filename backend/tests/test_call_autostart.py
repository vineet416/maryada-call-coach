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


def test_manager_example_link_and_summary_run_again_autostart_too():
    manager = text("pages", "Manager.tsx")
    link = re.search(r"<Link to=\{`/call/\$\{ex\.call_id\}`\}.*?className=", manager)
    assert link and "state={AUTOSTART}" in link.group(0) and "onClick={() => audio.unlock()}" in link.group(0)
    s = text("pages", "LiveCall.tsx")
    again = re.search(r"onRunAgain=\{\(\) => \{(.*?)\n          \}\}", s, re.DOTALL)
    assert again and "void audio.unlock()" in again.group(1) and "setAgain(true)" in again.group(1)  # inside the click
    assert "(autostart || again)" in s
    assert "Try another call" in text("pages", "CallReport.tsx")
    assert re.search(r"Try another call</Link>", text("pages", "CallReport.tsx"))
    assert not re.search(r"<Link[^\n]*next[^\n]*AUTOSTART", text("pages", "CallReport.tsx"))  # it goes to the Cases list


def test_call_page_waits_for_the_real_sound_probe_before_starting():
    s = text("pages", "LiveCall.tsx")
    assert "if (!soundAllowed())" in s and "setSoundBlocked(true)" in s
    flow = re.search(r"audio\.soundReady\(\)\.then\(\(ok\) => \{(.*?)\n    \}\)", s, re.DOTALL)
    assert flow, "the start must wait for the probe"
    body = flow.group(1)
    assert "if (ok) void begin('replay')" in body and "else blockSound()" in body  # a refused probe never starts the run
    assert "begin('live')" not in body


def test_a_refused_sound_ends_the_run_and_asks_for_one_tap():
    s = text("pages", "LiveCall.tsx")
    assert "audio.onBlocked(blockSound)" in s and "audio.onBlocked(null)" in s
    block = re.search(r"const blockSound = useCallback\(\(\) => \{(.*?)\n  \}, \[teardown\]\)", s, re.DOTALL)
    assert block
    for part in ("teardown()", "audio.stopAll()", "setSoundBlocked(true)", "setPhase('ready')"):
        assert part in block.group(1), part
    assert "'Tap to enable sound'" in s and "setSoundBlocked(false)" in s  # the tap starts a normal run


def test_audio_engine_probes_with_real_sound_and_reports_only_a_browser_refusal():
    e = text("lib", "audioEngine.ts")
    unlock = re.search(r"unlock\(\): Promise<boolean> \{(.*?)\n  \}", e, re.DOTALL)
    assert unlock and "muted" not in unlock.group(1) and "new Audio(SILENT_WAV)" in unlock.group(1)  # muted proves nothing
    assert "soundReady(): Promise<boolean>" in e and "?? Promise.resolve(false)" in e  # no click, no sound
    play = re.search(r"a\.play\(\)\.catch\(\(e: unknown\) => \{(.*?)\n    \}\)", e, re.DOTALL)
    assert play and "NotAllowedError" in play.group(1) and "this.turn === a" in play.group(1) and "onBlockedCb" in play.group(1)
    assert "play().catch(() => undefined)" not in e.split("playTurn(")[1].split("stopTurn()")[0]  # the rejection is not swallowed


def test_ready_card_stays_for_a_direct_load_and_is_hidden_only_while_autostarting():
    s = text("pages", "LiveCall.tsx")
    assert "Press start to allow sound" in s and "<StartCard" in s  # the fallback
    assert "const starting = ((autostart || again) && phase === 'ready') || (auto && (phase === 'ready' || phase === 'starting'))" in s
    assert "if (phase === 'loading' || !scenario || starting)" in s


def test_autostart_never_reaches_the_direct_routes():
    app = text("App.tsx")
    assert "AUTOSTART" not in app  # only in-app links carry the signal
    helper = text("lib", "autostart.ts")
    assert "hasBeenActive === true" in helper and "AUTOSTART = { autostart: true }" in helper
