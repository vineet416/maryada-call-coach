"""Manager page payload: the saved manager_data.json filtered by date, with the numbers recomputed by aggregate()."""
import json
from datetime import date

from .. import replay
from ..config import settings
from ..rules.loader import load_rules
from .aggregate import STATUS_RULE, aggregate


def load_saved() -> dict | None:
    """data/eval/manager_data.json, or None when it is missing or not a manager file."""
    try:
        d = json.loads((settings.data_dir / "eval" / "manager_data.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    ok = isinstance(d, dict) and all(isinstance(d.get(k), list) for k in ("calls", "roster")) and isinstance(d.get("source"), dict)
    return d if ok else None


def parse_day(value: str | None) -> str | None:
    """ISO date or None; ValueError for anything else."""
    return None if value is None else date.fromisoformat(value).isoformat()


def manager_payload(start: str | None, end: str | None) -> dict | None:
    saved = load_saved()
    if saved is None:
        return None
    agg = aggregate(saved["calls"], saved["roster"], start, end)
    for c in agg["calls"]:
        c["has_replay"] = replay.replay_path(c["call_id"]).exists()
    rules = load_rules()["rules"]
    days = sorted(c["call_date"] for c in saved["calls"])
    return {
        "generated_at": saved.get("generated_at"), "batch_label": saved.get("batch_label"), "source": saved["source"],
        "range": {"from": start, "to": end, "first_day": days[0] if days else None, "last_day": days[-1] if days else None},
        **agg, "status_rule": STATUS_RULE,
        "rules": [{"id": r["id"], "title": r["title"], "coach_line": (r.get("coach_lines") or [""])[0],
                   "review_only": r.get("kind_default") == "needs_review"}
                  for r in rules if r["id"].startswith("R")],
    }
