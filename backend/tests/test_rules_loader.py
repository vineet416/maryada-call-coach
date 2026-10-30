from app.rules.loader import load_rules


def test_rulebook_loads_all_rules_with_phrases_and_coach_lines():
    book = load_rules()
    rules = {r["id"]: r for r in book["rules"]}
    assert list(rules) == ["R1", "R2", "R3", "R4", "R5", "R6", "G1"]
    assert book["version"] == "rb-2026.11-v1"
    assert len(rules["R3"]["prefilter"]["strong"]) >= 25
    assert all(rules[rid]["coach_lines"] for rid in rules)
    assert rules["R3"]["weight"] == 30
