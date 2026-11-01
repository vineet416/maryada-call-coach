"""R2 (identification + recording notice) is judged on the completed second agent turn, script-tolerant, rule-based only."""
import pytest
import yaml
from app.config import settings
from app.rules.engine import deep_findings, fast_findings
from app.rules.prefilter import has_identification, prefilter, r2_missing
from app.rules.schemas import CallContext, LlmOut, Turn
from app.rules.text import skeleton

R2_CALLS = {"c22", "c23", "c24", "c28"}

# First two agent turns as the speech recognition returned them in the recorded runs (segments joined).
STT = {
    "c01": ["नमस्ते। सुरेश भोसले बोल रहे हैं।",
            "मैं नेहा तारंग Finserve से। यह call quality और training के लिए record हो रही है।"],
    "c06": ["Hello, स्मिता पाटिल बोल रही हैं।",
            "मैं रोहित बोल रहा हूँ तारंग Finserv से यह call quality और training के लिए record हो रही है।"],
    "c30": ["Good afternoon, नरेंद्र शिर्के जी।",
            "मैं नेहा तारंग Finserv से यह call record हो रही है। Quality और training के लिए बस 1 minute लूँगी।"],
    "c17": ["नमस्ते। सचिन लाड जी हैं।",
            ("मैं पूजा बोल रही हूँ Star Health Insurance से। यह call quality और training के लिए record हो रही है। "
             "सचिन जी कब तक आएंगे?")],
    "c25": ["नमस्ते। विजय घाडगे जी।",
            "प्रिया बोल रही हूँ तारंग Finserv से और यह call quality और training के लिए record हो रही है।"],
    "c20": ["Good evening. सुनील जी",
            ("पूजा बोल रही हूँ। तारंग Finserv से ध्यान रहे call record की जा रही है। इतनी late call के लिए sorry sir। "
             "बस 2 minute लूँगी।")],
    "c24": ["Hello madam, अनीता गाबड़े बोल रही हैं।",
            "Madam 5,400 की EMI bounce हुई है। 8 दिन से pending penalty भी लग रही है। पेमेंट कब कर रही हैं"],
}

_TO_ROMAN = {"कॉल": "call", "रिकॉर्ड": "record", "ट्रेनिंग": "training", "क्वालिटी": "quality", "फिनसर्व": "Finserv"}
_TO_DEV = {"record": "रिकॉर्ड", "ho": "हो", "rahi": "रही", "raha": "रहा", "hoon": "हूँ", "bol": "बोल", "se": "से", "main": "मैं"}


def _swap(text: str, table: dict[str, str]) -> str:
    return " ".join(table.get(w.strip(".,?!।").lower(), w) for w in text.split())


def _scenarios() -> list[dict]:
    out = []
    for p in sorted(settings.content_dir.glob("scenarios/*.yaml")):
        out += yaml.safe_load(p.read_text(encoding="utf-8"))["scenarios"]
    return out


def _agent_turns(sc: dict, field: str) -> list[str]:
    return [t[field] for t in sc["turns"] if t["s"] == "A"][:2]


def _fires(turns: list[str]) -> bool:
    """R2 as the engine produces it for the second agent turn (complete text)."""
    hist = [Turn(speaker="A", text=turns[0]), Turn(speaker="B", text="Haan ji.")]
    ctx = CallContext()
    return any(f.rule_id == "R2" for f in fast_findings(ctx, hist, 3, turns[1], complete=True))


def test_skeleton_is_the_same_across_scripts():
    assert skeleton("record") == skeleton("रिकॉर्ड") == "rkrd"
    assert skeleton("zaroori") == skeleton("ज़रूरी") == skeleton("जरूरी")
    assert skeleton("payment") == skeleton("पेमेंट")
    assert skeleton("bhej") == skeleton("भेज")
    assert skeleton("kuch") == skeleton("कुछ")


@pytest.mark.parametrize("cid", sorted(STT))
def test_real_transcribed_turns(cid):
    assert _fires(STT[cid]) is (cid in R2_CALLS)


def test_star_health_insurance_does_not_trigger_r2():
    assert has_identification(STT["c17"][1])
    assert not r2_missing(STT["c17"])


def test_all_30_scripts_in_roman_devanagari_and_mixed_script():
    scs = _scenarios()
    assert len(scs) == 30
    for sc in scs:
        roman, dev = _agent_turns(sc, "t"), _agent_turns(sc, "td")
        variants = {"roman": roman, "devanagari": dev,
                    "mixed_roman_words": [_swap(t, _TO_ROMAN) for t in dev],
                    "mixed_devanagari_words": [_swap(t, _TO_DEV) for t in roman]}
        for name, turns in variants.items():
            assert _fires(turns) is (sc["id"] in R2_CALLS), f"{sc['id']} {name}: {turns}"
    assert sum(1 for sc in scs if sc["id"] in R2_CALLS) == 4


def test_r2_never_on_partial_text_or_first_agent_turn():
    ctx = CallContext()
    hist = [Turn(speaker="A", text=STT["c01"][0]), Turn(speaker="B", text="Haan ji.")]
    partial = fast_findings(ctx, hist, 3, "मैं नेहा", complete=False)  # first segment of a proper introduction
    assert not [f for f in partial if f.rule_id == "R2"]
    assert not [f for f in fast_findings(ctx, [], 1, "Hello, EMI pending hai.", complete=True) if f.rule_id == "R2"]
    assert [f for f in fast_findings(ctx, hist, 3, "Kab tak payment karenge?", complete=True) if f.rule_id == "R2"]


def test_llm_r2_findings_are_dropped():
    out = LlmOut.model_validate({"findings": [{"rule_id": "R2", "confidence": 0.95, "quote": "विजय घाडगे जी"}]})
    assert not deep_findings(CallContext(), [], out, 1, "नमस्ते। विजय घाडगे जी।")


def test_r6_matches_mixed_script_pressing_phrase():
    ctx = CallContext(borrower_context="Borrower's father died yesterday.")
    for text in ("विजय जी, समझ सकती हूँ पर due date निकल चुकी है, कल तक payment जरूरी है, थोड़ा भी कर दो तो चलेगा।",
                 "Vijay ji, kal tak payment zaroori hai.", "आज ही कुछ भेज दीजिए।"):
        assert [f for f in prefilter(ctx, [], 7, text) if f.rule_id == "R6"], text
    assert not [f for f in prefilter(ctx, [], 7, "Aap araam se baat kijiye, hum baad mein call karenge.") if f.rule_id == "R6"]
