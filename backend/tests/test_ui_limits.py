"""The live-call limits shown on the Settings page must equal the backend defaults."""
import re
from pathlib import Path

from app.config import Settings

LIMITS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "limits.ts"


def _ts_number(name: str) -> float:
    m = re.search(rf"export const {name}\s*=\s*([0-9.]+)", LIMITS.read_text(encoding="utf-8"))
    assert m, f"{name} not found in frontend/src/lib/limits.ts"
    return float(m.group(1))


def test_call_length_matches_backend():
    assert _ts_number("CALL_LIMIT_S") == Settings.model_fields["session_max_s"].default


def test_concurrent_calls_match_backend():
    assert _ts_number("CONCURRENT_CALLS") == Settings.model_fields["max_live_sessions"].default
