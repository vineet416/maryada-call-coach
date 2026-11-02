"""Key pool of the offline evaluation runner: budget, switching and quota detection (no HTTP, no real keys)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from eval_keys import KeyPool, is_quota_error


def test_quota_error_detection():
    assert is_quota_error(403, "")
    assert is_quota_error(429, "Daily token limit reached")
    assert is_quota_error(429, "quota exceeded")
    assert not is_quota_error(429, "Too many requests, slow down")
    assert not is_quota_error(401, "daily")
    assert not is_quota_error(500, "quota")


def test_budget_caps_first_key_only():
    p = KeyPool("a", "b")
    p.add_tokens(900)
    assert not p.budget_reached(1000)
    p.add_tokens(100)
    assert p.budget_reached(1000) and p.can_switch()
    assert p.switch() == "b" and p.number == 2
    p.add_tokens(5000)
    assert not p.budget_reached(1000)  # the second key runs until Euri refuses it
    assert p.tokens == [1000, 5000] and not p.can_switch()


def test_single_key_and_no_budget():
    p = KeyPool("a")
    assert not p.can_switch() and not p.budget_reached(None)
    p.add_tokens(10)
    assert p.budget_reached(10)
    assert p.summary() == "key 1: 10 tokens"


def test_empty_second_key_is_ignored():
    assert len(KeyPool("a", "").keys) == 1
