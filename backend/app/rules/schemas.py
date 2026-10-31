"""Shared models for the rule engine."""
from typing import Literal

from pydantic import BaseModel, Field

Kind = Literal["violation", "advisory", "needs_review", "good_practice"]
Source = Literal["prefilter", "llm", "both", "gate"]


class CallContext(BaseModel):
    """Scenario facts the engine needs (docs/03 §3)."""
    answered_by: str = "borrower"
    simulated_start_time: str = "12:00"  # HH:MM, IST
    borrower_context: str = ""


class Turn(BaseModel):
    speaker: Literal["A", "B", "T"]
    text: str


class Finding(BaseModel):
    id: str = ""
    turn_idx: int = 0
    rule_id: str
    kind: Kind = "violation"
    confidence: float
    quote: str = ""
    token_range: tuple[int, int] = (0, 0)
    reason: str = ""
    rewrite: str = ""
    source: Source = "prefilter"
    phase: Literal["fast", "deep"] = "fast"


class LlmFinding(BaseModel):
    rule_id: Literal["R2", "R3", "R4", "R5", "R6"]
    confidence: float = Field(ge=0, le=1)
    quote: str
    reason: str = ""
    rewrite: str = ""
    kind: str = ""


class LlmGood(BaseModel):
    quote: str
    note: str = ""


class LlmOut(BaseModel):
    findings: list[LlmFinding] = Field(default_factory=list)
    good_practice: list[LlmGood] = Field(default_factory=list)


class RiskUpdate(BaseModel):
    score: int
    delta: int
    band: Literal["low", "medium", "high"]
    reason_rule_id: str | None = None
