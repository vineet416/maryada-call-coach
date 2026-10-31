"""Risk meter (docs/03 §3.7)."""
from .schemas import Finding, RiskUpdate

WEIGHT = {"R3": 30, "R5": 35, "R4": 35, "R1": 20, "R2": 8, "R6": 10}
NEEDS_REVIEW = 6
CLEAN_DECAY = -10


def band(score: int) -> str:
    return "low" if score < 30 else "medium" if score <= 60 else "high"


def finding_points(f: Finding) -> int:
    if f.kind == "good_practice":
        return 0
    if f.rule_id in ("R2", "R6"):
        return WEIGHT[f.rule_id]
    return WEIGHT[f.rule_id] if f.kind == "violation" else NEEDS_REVIEW


def update(score: int, findings: list[Finding]) -> RiskUpdate:
    """Apply one agent turn. Same rule several times in a turn counts once; no findings = -10."""
    per_rule: dict[str, int] = {}
    for f in findings:
        pts = finding_points(f)
        if f.kind != "good_practice":
            per_rule[f.rule_id] = max(per_rule.get(f.rule_id, 0), pts)
    if per_rule:
        delta = sum(per_rule.values())
        reason = max(per_rule, key=lambda r: (per_rule[r], WEIGHT[r]))
    else:
        delta, reason = CLEAN_DECAY, None
    new = max(0, min(100, score + delta))
    return RiskUpdate(score=new, delta=new - score, band=band(new), reason_rule_id=reason)
