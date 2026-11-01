"""Visitor credentials: request models (SecretStr) and the in-memory holder used by one session."""
from pydantic import BaseModel, Field, SecretStr

from . import redact


class GnaniIn(BaseModel):
    api_key: SecretStr = Field(max_length=300)


class LlmIn(BaseModel):
    base_url: str = Field(max_length=300)
    api_key: SecretStr = Field(max_length=300)
    model: str = Field(min_length=1, max_length=120)


class CredentialsIn(BaseModel):
    gnani: GnaniIn
    llm: LlmIn


class Creds:
    """The visitor's keys for one session. Memory only: never stored, never in repr/str, scrubbed from logs."""

    __slots__ = ("_registered", "base_url", "gnani_key", "llm_key", "model")

    def __init__(self, gnani_key: str, base_url: str, llm_key: str, model: str) -> None:
        self.gnani_key, self.base_url, self.llm_key, self.model = gnani_key, base_url, llm_key, model
        redact.register(gnani_key)
        redact.register(llm_key)
        self._registered = True

    def __repr__(self) -> str:
        return "Creds(<hidden>)"

    __str__ = __repr__

    def wipe(self) -> None:
        if self._registered:
            redact.unregister(self.gnani_key)
            redact.unregister(self.llm_key)
            self._registered = False
        self.gnani_key = self.llm_key = ""

    @classmethod
    def from_body(cls, c: CredentialsIn) -> "Creds":
        return cls(c.gnani.api_key.get_secret_value().strip(), c.llm.base_url.strip(),
                   c.llm.api_key.get_secret_value().strip(), c.llm.model.strip())
