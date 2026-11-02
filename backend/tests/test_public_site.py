"""What a visitor can read: no authors' notes, no internal wording, links only to recorded runs.
The frontend has no test runner, so the page rules are checked on its source text and on the data the pages are built from."""
import re
from pathlib import Path

import pytest
from app import replay
from app.api import rest
from app.manager.data import manager_payload
from app.session import assets

SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"
PAGES = sorted([*(SRC / "pages").glob("*.tsx"), *(SRC / "components").rglob("*.tsx")])
FORBIDDEN_NOTES = re.compile(r"hard[ _-]?negative|must not be flagged|\bCONTROL\b|\bHERO\b", re.IGNORECASE)


def source(name: str) -> str:
    return (SRC / "pages" / name).read_text(encoding="utf-8")


def rendered_lines(path: Path):
    """Source lines that can reach the screen: comments and imports are skipped."""
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        t = line.strip()
        if t.startswith(("//", "/*", "*", "import ")) or "http" in t:
            continue
        yield n, re.sub(r"\s//\s.*$", "", line)


# ---- authors' notes never reach a visitor
def test_public_summary_removes_the_authors_notes():
    assert assets.public_summary("Hard negative: agent truthfully mentions late fee; must NOT be flagged.") == "Agent truthfully mentions late fee."
    assert assets.public_summary("CONTROL / hard negative: spouse answers; agent only leaves a callback request. Must NOT be flagged.") == (
        "Spouse answers; agent only leaves a callback request.")
    assert assets.public_summary("HERO. Agent threatens police.") == "Agent threatens police."
    assert assets.public_summary("Agent identifies properly, listens.") == "Agent identifies properly, listens."


def test_every_case_summary_the_api_returns_is_free_of_notes():
    for c in rest.list_scenarios():
        assert not FORBIDDEN_NOTES.search(c["summary"]), (c["id"], c["summary"])
        assert c["summary"][:1].isupper() and c["summary"].endswith("."), (c["id"], c["summary"])
        assert not FORBIDDEN_NOTES.search(rest.get_scenario(c["id"])["summary"])


@pytest.mark.parametrize("path", PAGES, ids=lambda p: p.name)
def test_no_page_renders_internal_wording(path):
    bad = re.compile(r"hard[ _-]?negative|must not be flagged|docs/\d|DECISIONS|\.yaml|Decision \d|\bC\d{1,2} (gate|checkpoint)\b", re.IGNORECASE)
    hits = [(n, line.strip()) for n, line in rendered_lines(path) if bad.search(line)]
    assert not hits, hits


@pytest.mark.parametrize("path", [p for p in PAGES if p.name != "Evaluation.tsx"], ids=lambda p: p.name)
def test_evaluation_jargon_stays_on_the_evaluation_page(path):
    hits = [(n, line.strip()) for n, line in rendered_lines(path) if re.search(r"held[- ]out|seen in development|ablation|labels hash", line, re.IGNORECASE)]
    assert not hits, hits


# ---- Manager: links only to recorded runs
def test_manager_example_links_point_to_recorded_runs():
    payload = manager_payload(None, None)
    assert payload is not None
    calls = {c["call_id"]: c for c in payload["calls"]}
    linked = [calls[a["example_call_id"]] for a in payload["agents"] if a.get("example_call_id") in calls and calls[a["example_call_id"]]["has_replay"]]
    for c in linked:  # a link is drawn only for these, and each has a saved run
        assert replay.replay_path(c["call_id"]).exists(), c["call_id"]
    plain = [a["example_call_id"] for a in payload["agents"] if a.get("example_call_id") in calls and not calls[a["example_call_id"]]["has_replay"]]
    assert all(not replay.replay_path(cid).exists() for cid in plain)  # the rest are shown as plain text


@pytest.mark.parametrize("name", ["Manager.tsx", "ManagerAgent.tsx"])
def test_every_call_link_on_the_manager_pages_is_guarded_by_a_recorded_run(name):
    lines = source(name).splitlines()
    links = [i for i, line in enumerate(lines) if "`/call/" in line]
    assert links, "the page should still link to recorded calls"
    for i in links:
        assert any("has_replay" in ln for ln in lines[max(0, i - 4):i]), f"{name}:{i + 1} links to a call that may have no recorded run"


# ---- the other pages
def test_home_lists_only_recorded_runs_without_all_or_recorded_chips():
    s = source("Cases.tsx")
    assert "listed.filter" in s and "all.filter((c) => {" not in s
    assert "Recorded runs {" not in s and ">All {" not in s
    assert "recorded runs of synthetic calls" in s and "Clean calls" in s


def test_call_page_without_a_recording_shows_only_title_and_one_line():
    s = source("LiveCall.tsx")
    assert "This call has no recorded run" in s and "!scenario.has_replay && !LIVE_CALLS_ENABLED" in s


def test_settings_hides_key_forms_and_limits_until_speak_live_is_on():
    s = source("Settings.tsx")
    assert s.count("SPEAK_LIVE_ENABLED &&") >= 3  # key forms, "How your keys are handled", "Live call limits"
    assert "MIC_CALL_LIMIT_S" in s and not re.search(r"(?<!MIC_)CALL_LIMIT_S", s) and "200" not in s
    assert "Preferences" in s and "Browse recorded runs" in s


def test_how_it_works_says_upload_is_coming_soon():
    s = source("HowItWorks.tsx")
    assert "Upload is coming soon." in s and "Bring your own recordings" not in s


def test_evaluation_page_is_the_slim_layout():
    s = source("Evaluation.tsx")
    for gone in ("F1", "f1", "PerCall", "RunPicker", "Coverage", "hard_negative", "off / on label", "Time to flag", "Tuning calls"):
        assert gone not in s, gone
    for kept in ("Count needs-review as found", "How these numbers were produced", "Where it went wrong", "Honest limits"):
        assert kept in s, kept
    assert s.count("<li>") >= 5 and s.count("<li>Synthetic") == 1  # the five limits are fixed text, numbers come from the data
