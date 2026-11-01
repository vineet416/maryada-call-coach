"""Pure-function tests: short-segment skip guard and LLM result cache keys."""
import pytest
from app.rules import llm
from app.rules.engine import fast_findings
from app.rules.schemas import CallContext, Turn
from app.rules.skip import should_skip

CTX = CallContext(answered_by="borrower", simulated_start_time="11:00")


WARM = [Turn(speaker="A", text="Namaste"), Turn(speaker="B", text="Haan"), Turn(speaker="A", text="Main Rohit bol raha hoon")]


def _skip(text, ctx=CTX, history=None):
    h = WARM if history is None else history
    return should_skip(ctx, h, text, fast_findings(ctx, h, 3, text))


def test_first_two_agent_turns_are_never_skipped():
    assert not _skip("Namaste sir.", history=[])
    assert not _skip("Main Rohit bol raha hoon.", history=[Turn(speaker="A", text="Namaste"), Turn(speaker="B", text="Haan")])
    assert _skip("Theek hai, Friday pakka.", history=WARM)  # third agent turn: the guarded skip applies again


def test_short_clean_text_is_skipped():
    assert _skip("Theek hai, Friday pakka.")


def test_long_text_is_not_skipped():
    assert not _skip("Theek hai sir toh phir hum Friday ko milte hain aur payment ho jayega na")


def test_prefilter_hit_blocks_skip():
    assert not _skip("Sharam karo, sir.")  # R3 strong phrase, 3 words


def test_lexicon_keyword_blocks_skip():
    # R4 gate is off for a borrower, so the prefilter is silent, but the lexicon still blocks the skip
    assert fast_findings(CTX, WARM, 3, "Unka loan default hai.") == []
    assert not _skip("Unka loan default hai.")


def test_earlier_borrower_occasion_blocks_skip():
    hist = [*WARM, Turn(speaker="B", text="Mere pitaji guzar gaye hain")]
    assert not _skip("Okay, theek hai.", history=hist)


def test_borrower_context_blocks_skip():
    assert not _skip("Okay sir.", ctx=CallContext(borrower_context="mother in hospital"))


def test_cache_key_ignores_nothing_but_the_prompt():
    m1 = llm._messages(CTX, [], "Namaste sir")
    m2 = llm._messages(CTX, [], "Namaste sir")
    m3 = llm._messages(CTX, [], "Namaste madam")
    assert llm.cache_key("m", "u", m1) == llm.cache_key("m", "u", m2)
    assert llm.cache_key("m", "u", m1) != llm.cache_key("m", "u", m3)
    assert llm.cache_key("m", "u", m1) != llm.cache_key("n", "u", m1)
    assert llm.cache_key("m", "u", m1) != llm.cache_key("m", "v", m1)


@pytest.fixture
def clean_cache():
    llm._CACHE.clear()
    yield
    llm._disk = None
    llm._CACHE.clear()


def test_disk_cache_round_trip(tmp_path, clean_cache):
    path = tmp_path / "cache.jsonl"
    llm.enable_disk_cache(path)
    llm._cache_put("m|abc", '{"findings":[],"good_practice":[]}')
    llm._CACHE.clear()
    assert llm.enable_disk_cache(path) == 1
    assert llm._CACHE["m|abc"].startswith("{")
