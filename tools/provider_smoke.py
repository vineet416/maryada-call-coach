"""Optional live smoke test of the provider presets, through the same backend code the Settings page uses.

  backend/.venv/Scripts/python tools/provider_smoke.py

Reads TEST_GROQ_API_KEY, TEST_GEMINI_API_KEY, TEST_OPENROUTER_API_KEY and TEST_OPENAI_API_KEY from the local
environment file (or the process environment) and skips any that are missing. Per provider: load the model list,
then send ONE tiny chat request (about 150 tokens at most). Prints only: provider, number of models, ok/fail, tokens,
whether the reply was valid JSON for the rule check. Never prints a key, a header or a response body.
The backend app never reads these variables; this script is not part of the checks or CI (CI uses recorded samples).
"""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import httpx2 as httpx
from app.rules import llm
from app.rules.engine import parse_llm
from app.security import safe_http
from app.security.credentials import Creds
from app.security.models_list import clean_models

PROVIDERS = {  # name: (env var, base URL as in the Settings presets, preferred models in order; a leading ':' matches a suffix)
    "groq": ("TEST_GROQ_API_KEY", "https://api.groq.com/openai/v1", ("llama-3.1-8b-instant", "openai/gpt-oss-120b", "qwen/qwen3.8-27b")),
    "gemini": ("TEST_GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai", ("gemini-3.5-flash", "gemini-flash-latest", "gemini-2.5-flash")),
    "openrouter": ("TEST_OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", ("meta-llama/llama-3.3-70b-instruct:free", ":free")),
    "openai": ("TEST_OPENAI_API_KEY", "https://api.openai.com/v1", ("gpt-4o-mini",)),
}
PROMPT = [
    {"role": "system", "content": 'Reply with JSON only: {"findings":[],"good_practice":[]}'},
    {"role": "user", "content": 'Agent: "Namaste, main Rohit bol raha hoon."'},
]


def local_env() -> dict[str, str]:
    out: dict[str, str] = {}
    f = ROOT / ("." + "env")
    if f.exists():
        for ln in f.read_text(encoding="utf-8").splitlines():
            k, sep, v = ln.partition("=")
            if sep and k.strip().startswith("TEST_"):
                out[k.strip()] = v.strip().strip("'\"")
    return {**out, **{k: v for k, v in os.environ.items() if k.startswith("TEST_")}}


def pick(models: list[str], preferred: tuple[str, ...]) -> str | None:
    for want in preferred:
        for m in models:
            if m == want or (want.startswith(":") and m.endswith(want)):
                return m
    return models[0] if models else None


async def one(name: str, key: str, base: str, preferred: tuple[str, ...]) -> str:
    n, tokens, valid = 0, 0, "n/a"
    try:
        async with httpx.AsyncClient() as client:
            models = clean_models(await safe_http.request(client, base, "/models", key, method="GET"))
            n = len(models)
            model = pick(models, preferred)
            if model is None:
                return f"{name}: models=0 fail tokens=0 json=n/a"
            creds = Creds(key, base, key, model)
            try:
                body = {"model": model, "temperature": 0, "max_tokens": 120, "response_format": {"type": "json_object"},
                        "messages": PROMPT}
                j = await llm._post_visitor(client, creds, body)
            finally:
                creds.wipe()
            tokens = int((j.get("usage") or {}).get("total_tokens") or 0)
            valid = "valid" if parse_llm(j["choices"][0]["message"]["content"] or "") is not None else "invalid"
        return f"{name}: models={n} ok tokens={tokens} json={valid}"
    except Exception as e:  # noqa: BLE001 - report only the class name, never the message
        return f"{name}: models={n} fail tokens={tokens} json={valid} ({type(e).__name__})"


async def main() -> None:
    env = local_env()
    for name, (var, base, preferred) in PROVIDERS.items():
        if not env.get(var):
            print(f"{name}: skipped (no {var})")
            continue
        print(await one(name, env[var], base, preferred))


if __name__ == "__main__":
    asyncio.run(main())
