"""Two Euri keys for the offline evaluation runner (never imported by the app server).

The first key is used until the run's token budget for it is reached or Euri says its daily allowance is spent; then the
second key (if present) takes over for the rest of the run. Only counts are ever reported, never key values.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


def second_key(env_file) -> str:
    """EURI_API_KEY2 from the environment or the .env file ('' if absent)."""
    class _Second(BaseSettings):
        model_config = SettingsConfigDict(env_file=env_file, extra="ignore")
        euri_api_key2: str = ""
    return _Second().euri_api_key2


def is_quota_error(status: int, body: str) -> bool:
    """True when Euri reports the daily allowance spent: any 403, or a 429 whose message names a daily limit or quota.
    A plain per-minute 429 is not a quota error (switching keys would not help and it would burn the second key)."""
    if status == 403:
        return True
    low = body.lower()
    return status == 429 and ("daily" in low or "quota" in low)


class KeyPool:
    def __init__(self, key1: str, key2: str = "") -> None:
        self.keys = [k for k in (key1, key2) if k]
        self.active = 0
        self.tokens = [0] * len(self.keys)  # reported tokens used per key in this run

    @property
    def number(self) -> int:
        """1 or 2: which key is active (for messages)."""
        return self.active + 1

    @property
    def key(self) -> str:
        return self.keys[self.active]

    def add_tokens(self, n: int) -> None:
        self.tokens[self.active] += n

    def budget_reached(self, budget: int | None) -> bool:
        """The budget caps the first key only; the second key runs until Euri refuses it."""
        return budget is not None and self.active == 0 and self.tokens[0] >= budget

    def can_switch(self) -> bool:
        return self.active + 1 < len(self.keys)

    def switch(self) -> str:
        """Move to the next key and return its value (the caller puts it in the settings object)."""
        self.active += 1
        return self.keys[self.active]

    def summary(self) -> str:
        return ", ".join(f"key {i + 1}: {t} tokens" for i, t in enumerate(self.tokens))
