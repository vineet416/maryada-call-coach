"""Loads the rulebook: rule metadata from rules.yaml, phrases and coach lines from rules_phrases.yaml."""
from functools import lru_cache
from typing import Any

import yaml

from ..config import settings


def _read(name: str) -> dict[str, Any]:
    with open(settings.content_dir / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache
def load_rules() -> dict[str, Any]:
    book = _read("rules.yaml")
    phrases = _read("rules_phrases.yaml")
    if book["version"] != phrases["version"]:
        raise ValueError("rules.yaml and rules_phrases.yaml versions differ")
    for rule in book["rules"]:
        rid = rule["id"]
        rule["prefilter"] = phrases["rules"].get(rid, {})
        rule["coach_lines"] = phrases["coach_lines"].get(rid, [])
    return book
