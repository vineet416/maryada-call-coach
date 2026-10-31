"""Scenarios, the audio manifest and coach lines (all authored files; nothing is hard-coded here)."""
import json
from functools import lru_cache
from pathlib import Path

import yaml

from ..config import settings
from ..rules.loader import load_rules
from ..rules.schemas import CallContext

SPEAKER = {"A": "agent", "B": "borrower", "T": "third_party"}


def audio_dir() -> Path:
    return settings.data_dir / "audio"


@lru_cache
def scenarios() -> dict[str, dict]:
    out = {}
    for f in sorted((settings.content_dir / "scenarios").glob("*.yaml")):
        for sc in yaml.safe_load(f.read_text(encoding="utf-8"))["scenarios"]:
            out[sc["id"]] = sc
    return out


@lru_cache
def audio_manifest() -> dict:
    p = audio_dir() / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


@lru_cache
def coach_manifest() -> dict:
    p = audio_dir() / "coach_manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"lines": []}


def has_audio(scenario_id: str) -> bool:
    return scenario_id in audio_manifest()


def context_for(sc: dict) -> CallContext:
    return CallContext(answered_by=sc.get("answered_by", "borrower"), simulated_start_time=sc.get("time", "12:00"),
                       borrower_context=sc.get("borrower_context", ""))


def coach_line(rule_id: str, used: int) -> dict | None:
    """Rotate through the rule's coach lines (n = used % lines + 1): text for the card, file and duration for the voice."""
    lines = [ln for ln in coach_manifest()["lines"] if ln["rule"] == rule_id]
    texts = load_rules()["rules"]
    texts = next((r["coach_lines"] for r in texts if r["id"] == rule_id), [])
    if not lines or not texts:
        return None
    ln = lines[used % len(lines)]
    return {"text": texts[min(ln["n"], len(texts)) - 1], "audio_url": f"/audio/coach/{ln['file']}",
            "duration_ms": ln["duration_ms"]}


def rbi_ref(rule_id: str) -> str:
    return next((r.get("rbi_ref", "") for r in load_rules()["rules"] if r["id"] == rule_id), "")
