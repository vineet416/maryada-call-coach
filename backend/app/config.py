import logging
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
log = logging.getLogger("maryada")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    gnani_api_key_id: str = ""
    gnani_stt_ws_url: str = "wss://api.vachana.ai/stt/v3/stream"
    gnani_stt_rest_url: str = "https://api.vachana.ai/stt/v3"
    gnani_tts_url: str = "https://api.vachana.ai/api/v1/tts/inference"
    euri_api_key: str = ""
    euri_base_url: str = "https://api.euron.one/api/v1/euri"
    llm_http2: bool = True  # HTTP/2 for Euri; falls back to HTTP/1.1 if negotiation fails
    llm_model: str = "gpt-5.4-mini"
    llm_fallback_model: str = "gpt-4.1-mini"
    skip_llm_max_words: int = 8  # agent text under this many words may skip the LLM (see rules/skip.py for the guard)
    stt_mode: str = "realtime"
    server_keys_enabled: bool = False  # True only for local development and the evaluation tools (env keys are read)
    max_live_sessions: int = 3  # concurrent live sessions (visitor keys)
    replay_only: bool = False
    allowed_origins: str = "http://localhost:5173"
    pace: float = 1.0
    session_max_s: float = 200.0  # per-session limit (docs/01 §8; raised from 150 s on 2026-10-31)
    record_runs: bool = False  # save each live run to data/replay/_runs/ (for picking the demo recording)
    check_granularity: str = "segment"  # segment | turn (docs/13 §4.1)

    content_dir: Path = ROOT / "content"
    data_dir: Path = ROOT / "data"
    db_path: Path = ROOT / "data" / "maryada.db"

    @property
    def server_keys(self) -> bool:
        """Env keys may be used for live sessions only when SERVER_KEYS_ENABLED is on AND both are present."""
        return self.server_keys_enabled and bool(self.gnani_api_key_id and self.euri_api_key)

    @property
    def live_capable(self) -> bool:
        """Live calls are possible (with the visitor's own keys, or server keys in development) unless REPLAY_ONLY."""
        return not self.replay_only

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()
