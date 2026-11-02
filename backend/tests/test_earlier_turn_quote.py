"""A model finding whose quote belongs to an earlier turn the model was shown is dropped (no model, no files)."""
import pytest
from app.rules.engine import deep_findings
from app.rules.schemas import CallContext, LlmOut, Turn


def out(rule, quote, conf=0.74):
    return LlmOut.model_validate({"findings": [{"rule_id": rule, "confidence": conf, "quote": quote}]})


def run(text, history, rule, quote, conf=0.74):
    return deep_findings(CallContext(), [], out(rule, quote, conf), 11, text, history)


CASES = [  # (call, flagged turn, earlier agent turn shown as context, borrower reply in between, rule, quote)
    ("c07 t11", "ठीक है Friday को 5,000 पक्का मैं नोट कर लेती हूँ UPI से कर देना।",
     "भागने का सोचना भी मत, सीधे-सीधे बोलो कब दोगे, वरना मुझसे बुरा कोई नहीं होगा",
     "Madam, ऐसे डर से बात मत करो, Friday को 5,000 दे दूंगा, बाकी next month.", "R3", "वरना मुझसे बुरा कोई नहीं होगा"),
    ("c12 t9", "हाँ madam, इसलिए आज ही भर दीजिए, थोड़ा भी भर दो तो चलेगा",
     ("अगले महीने तक? रेखा जी, यह नहीं चलेगा, देखिए मैं RBI की तरफ से भी बोल रही हूँ, RBI आपका loan account block कर देगी "
      "और आपको किसी bank से loan नहीं मिलेगा जिंदगी भर।"),
     "क्या RBI ऐसा हो सकता है क्या? मेरे को तो पता ही नहीं था।", "R5",
     "मैं RBI की तरफ से भी बोल रही हूँ, RBI आपका loan account block कर देगी और आपको किसी bank से loan नहीं मिलेगा जिंदगी भर।"),
    ("c13 t9", "इसलिए Friday से पहले कर दीजिए sir, आज कल में हो जाए तो best है, पूरा नहीं हो तो थोड़ा अभी कर दो बाकी Friday को।",
     "सर, मैं clear बोल रहा हूँ Friday तक, पक्का ना? अगर Friday तक नहीं दिया तो हर दिन 5,000 रुपये penalty लगेगी और यह RBI का rule है।",
     "5,000 रोज? इतना कैसे लगेगा?", "R5",
     "अगर Friday तक नहीं दिया तो हर दिन 5,000 रुपये penalty लगेगी और यह RBI का rule है।"),
]


@pytest.mark.parametrize("name,text,earlier,reply,rule,quote", CASES, ids=[c[0] for c in CASES])
def test_quote_from_an_earlier_turn_is_dropped(name, text, earlier, reply, rule, quote):
    history = [Turn(speaker="A", text=earlier), Turn(speaker="B", text=reply)]
    assert not [f for f in run(text, history, rule, quote) if f.rule_id == rule]
    # without the context turns the old behaviour stays (a weak needs-review finding)
    kept = [f for f in run(text, [], rule, quote) if f.rule_id == rule]
    assert len(kept) == 1 and kept[0].kind == "needs_review"


def test_a_genuine_paraphrase_of_this_turn_is_kept():
    text = "Agar kal tak payment nahi aaya to hum aapka ghar seize kar lenge, soch lijiye."
    earlier = [Turn(speaker="A", text="Namaste, main Rohan bol raha hoon."), Turn(speaker="B", text="Haan boliye.")]
    near = run(text, earlier, "R3", "agar kal tak payment na aaya to ghar seize ho jayega", conf=0.9)
    assert [x.rule_id for x in near] == ["R3"]  # close wording aligns normally
    far = run(text, earlier, "R3", "we will take your house tomorrow", conf=0.9)  # no overlap: whole-sentence fallback
    assert [x.rule_id for x in far] == ["R3"] and far[0].kind == "needs_review"  # still capped, not dropped


def test_an_exact_quote_in_this_turn_is_kept_even_if_it_repeats_an_earlier_turn():
    line = "Friday tak nahi diya to penalty lagegi"
    history = [Turn(speaker="A", text=line + "."), Turn(speaker="B", text="Kya?")]
    f = run("Main phir bol raha hoon, " + line + ", samjhe?", history, "R5", line, conf=0.95)
    assert [x.kind for x in f if x.rule_id == "R5"] == ["violation"]
