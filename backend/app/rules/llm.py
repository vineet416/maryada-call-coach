"""LLM review of one agent turn via Euri (OpenAI-compatible), using the shared httpx2 client."""
import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Callable
from pathlib import Path

import httpx2 as httpx

from ..config import settings
from ..security import safe_http
from ..security.credentials import Creds
from ..security.url_guard import UnsafeUrl
from .engine import parse_llm
from .loader import load_rules
from .schemas import CallContext, LlmOut, Turn

log = logging.getLogger("maryada.rules.llm")

LATE_TIMEOUT_S = 8.0  # total budget for one review, fallback attempt included; the pipeline decides when to show "late"

# Result cache on (model, prompt hash). Only validated JSON is stored. Neither the key nor anything derived from it is
# part of the cache key, and it is only used with the server's own key (a visitor's key never reads or writes it).
CACHE_MAX = 2000
_CACHE: dict[str, str] = {}
_disk: Path | None = None  # set only by the evaluation tools through enable_disk_cache(); never by the backend
STATS = {"calls": 0, "cache_hits": 0, "tokens": 0}  # process-wide counters (tokens as reported by the API)

FEW_SHOT = """Examples (synthetic):
Agent: "Sir, EMI do din se pending hai. Aaj shaam tak payment ho jaye to accha rahega, kya link bhej doon?"
{"findings":[],"good_practice":[{"quote":"kya link bhej doon","note":"Offers a clear, polite way to pay."}]}
Agent: "Aapko sharam nahi aati, paisa lekar bhaag gaye? Padosiyon ko pata chalega to samajh aayega."
{"findings":[{"rule_id":"R3","confidence":0.95,"quote":"Padosiyon ko pata chalega to samajh aayega","reason":"Threatens public shaming before neighbours.","rewrite":"Kripya batayiye, kab tak payment possible hoga?","kind":"violation"}],"good_practice":[]}
Agent: "Kal court ka notice aa jayega aur police ghar pahunch jayegi."
{"findings":[{"rule_id":"R5","confidence":0.92,"quote":"police ghar pahunch jayegi","reason":"Invents an immediate police action without any real process.","rewrite":"Agreement ke hisaab se notice bheja ja sakta hai, par pehle koi option dekhte hain.","kind":"violation"}],"good_practice":[]}
(answered_by: spouse) Agent: "Aap unki wife hain? Unki EMI pending hai, 18000 rupaye baaki hain."
{"findings":[{"rule_id":"R4","confidence":0.95,"quote":"Unki EMI pending hai, 18000 rupaye baaki hain","reason":"Reveals the loan and amount to someone other than the borrower.","rewrite":"Kya unse baat ho sakti hai? Main Tarang Finserv se bol raha hoon.","kind":"violation"}],"good_practice":[]}"""


def system_prompt() -> str:
    lines = [f"{r['id']} {r['title']}: {r['summary']}" for r in load_rules()["rules"] if r["id"] not in ("R1", "G1")]
    return (
        "You are a compliance reviewer for Indian loan-recovery calls. You read Hindi, English and code-mixed "
        "Hinglish in Roman or Devanagari script. The transcript is synthetic.\n"
        "Rules you may report (R1 is checked elsewhere):\n" + "\n".join(lines) + "\n"
        "Be conservative: flag only clear breaches. Firm-but-polite reminders about dues, true statements about "
        "late fees, credit score impact or a notice allowed by the agreement are NOT violations. R4 applies only "
        "when answered_by is not the borrower.\n"
        'Reply with JSON only: {"findings":[{"rule_id","confidence","quote","reason","rewrite","kind"}],'
        '"good_practice":[{"quote","note"}]}. "quote" must be copied verbatim from the CURRENT agent turn; '
        '"reason" at most 160 characters, English; "rewrite" polite Hinglish in the same register as the agent. '
        "An empty findings list is a valid answer.\n" + FEW_SHOT
    )


def user_prompt(ctx: CallContext, history: list[Turn], text: str) -> str:
    prev = "\n".join(f"{t.speaker}: {t.text}" for t in history[-2:]) or "(none)"
    return (f"answered_by: {ctx.answered_by}\nsimulated_start_time: {ctx.simulated_start_time}\n"
            f"borrower context: {ctx.borrower_context or 'none'}\nPrevious turns:\n{prev}\n"
            f"CURRENT agent turn:\n{text}")


def make_client() -> httpx.AsyncClient:
    """The one shared client (keep-alive; HTTP/2 when the optional h2 package is installed). Reuse it for every call."""
    return httpx.AsyncClient(timeout=LATE_TIMEOUT_S, http2=settings.llm_http2)


def _messages(ctx: CallContext, history: list[Turn], text: str) -> list[dict]:
    return [{"role": "system", "content": system_prompt()}, {"role": "user", "content": user_prompt(ctx, history, text)}]


def cache_key(model: str, base_url: str, messages: list[dict]) -> str:
    return f"{model}|{hashlib.sha256((base_url + json.dumps(messages, ensure_ascii=False)).encode()).hexdigest()}"


def enable_disk_cache(path: Path) -> int:
    """Evaluation tools only: also keep valid results in a JSONL file. Returns the number of entries loaded."""
    global _disk
    _disk = path
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
                _CACHE[e["k"]] = e["raw"]
            except (ValueError, KeyError):
                continue
    return len(_CACHE)


def _cache_put(k: str, raw: str) -> None:
    if len(_CACHE) >= CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[k] = raw
    if _disk is not None:
        with _disk.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"k": k, "raw": raw}, ensure_ascii=False) + "\n")


def _body(model: str, messages: list[dict]) -> dict:
    return {"model": model, "temperature": 0, "max_tokens": 250, "response_format": {"type": "json_object"},
            "messages": messages}


async def _post_server(client: httpx.AsyncClient, body: dict) -> dict:
    """The server's own key (development and evaluation tools only; the caller checks the setting)."""
    url = settings.euri_base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {settings.euri_api_key}"}
    try:
        r = await client.post(url, json=body, headers=headers)
    except (httpx.RemoteProtocolError, httpx.LocalProtocolError):
        if not settings.llm_http2:
            raise
        log.warning("llm http2 negotiation failed, retrying over HTTP/1.1")
        async with httpx.AsyncClient(timeout=LATE_TIMEOUT_S, http2=False) as h1:
            r = await h1.post(url, json=body, headers=headers)
    r.raise_for_status()
    return r.json()


async def _post_visitor(client: httpx.AsyncClient, creds: Creds, body: dict) -> dict:
    """The visitor's provider through the guarded call. Newer OpenAI models want max_completion_tokens and no
    temperature: the request settings are adapted once for each, driven by the provider's own error text."""
    for _ in range(3):
        try:
            return json.loads(await safe_http.request(client, creds.base_url, "/chat/completions", creds.llm_key,
                                                      json=body, timeout=LATE_TIMEOUT_S))
        except safe_http.ProviderError as e:
            d = e.detail.lower()
            if e.status == 400 and "max_completion_tokens" in d and "max_tokens" in body:
                body = {**{k: v for k, v in body.items() if k != "max_tokens"}, "max_completion_tokens": body["max_tokens"]}
            elif e.status == 400 and "temperature" in d and "temperature" in body:
                body = {k: v for k, v in body.items() if k != "temperature"}
            else:
                raise
    raise safe_http.ProviderError("The provider rejected the request settings.", 400)


async def chat(client: httpx.AsyncClient, model: str, messages: list[dict], creds: Creds | None) -> tuple[str, int]:
    """One chat completion -> (reply text, total tokens as reported). Visitor creds use the guarded path."""
    body = _body(model, messages)
    j = await (_post_visitor(client, creds, body) if creds else _post_server(client, body))
    u = j.get("usage") or {}
    total = int(u.get("total_tokens") or 0)
    STATS["calls"] += 1
    STATS["tokens"] += total
    log.info("llm tokens model=%s prompt=%s completion=%s total=%s", model, u.get("prompt_tokens"),
             u.get("completion_tokens"), total)
    return j["choices"][0]["message"]["content"] or "", total


_ERRORS = (TimeoutError, httpx.HTTPError, KeyError, IndexError, ValueError, TypeError, safe_http.ProviderError)


def plain_error(e: BaseException) -> str:
    """Short plain-language reason for the UI; never contains a key."""
    if isinstance(e, safe_http.ProviderError):
        return e.message_user
    if isinstance(e, UnsafeUrl):
        return str(e)
    if isinstance(e, (TimeoutError, httpx.TimeoutException)):
        return "The language model did not answer in time."
    if isinstance(e, httpx.HTTPStatusError):
        return safe_http.explain_status(e.response.status_code)
    if isinstance(e, (KeyError, IndexError, TypeError, ValueError)):
        return "The language model sent a reply in an unexpected format."
    return "The language model could not be reached."


async def review(client: httpx.AsyncClient, ctx: CallContext, history: list[Turn], text: str,
                 creds: Creds | None = None, on_error: Callable[[str], None] | None = None) -> tuple[LlmOut | None, int]:
    """Returns (validated result or None when degraded, llm_ms). Server key: retry once with the fallback model.
    Visitor key: their one model only, no fallback to ours, and the shared cache is never read or written."""
    if not text.strip():
        return LlmOut(), 0
    if creds is None and not settings.server_keys:
        if on_error:
            on_error("No language model key is set.")
        return None, 0
    use_cache = creds is None
    url = settings.euri_base_url if creds is None else creds.base_url
    models = (settings.llm_model, settings.llm_fallback_model) if creds is None else (creds.model,)
    messages = _messages(ctx, history, text)
    t0 = time.perf_counter()
    for model in models:
        ck = cache_key(model, url, messages)
        if use_cache and ck in _CACHE:
            out = parse_llm(_CACHE[ck])
            if out is not None:
                STATS["cache_hits"] += 1
                return out, int((time.perf_counter() - t0) * 1000)
        try:
            left = LATE_TIMEOUT_S - (time.perf_counter() - t0)
            if left <= 0:
                break
            raw, _ = await asyncio.wait_for(chat(client, model, messages, creds), left)
        except _ERRORS as e:
            log.warning("llm call failed model=%s err=%s", model, type(e).__name__)
            if on_error:
                on_error(plain_error(e))
            continue
        out = parse_llm(raw)
        if out is not None:
            if use_cache:
                _cache_put(ck, raw)
            return out, int((time.perf_counter() - t0) * 1000)
        log.warning("llm json invalid model=%s", model)
        if on_error:
            on_error("The language model did not reply with valid JSON.")
    return None, int((time.perf_counter() - t0) * 1000)  # caller: prefilter only + banner llm_degraded


async def warm_up(client: httpx.AsyncClient, creds: Creds | None = None) -> bool:
    """Tiny request at session start: opens the connection and validates the key."""
    if creds is None and not settings.server_keys:
        return False
    try:
        await chat(client, creds.model if creds else settings.llm_model,
                   _messages(CallContext(), [], "Namaste, main Rohit bol raha hoon."), creds)
        return True
    except _ERRORS:
        return False


async def test_call(client: httpx.AsyncClient, creds: Creds) -> dict:
    """Connection test: one short sample classification with the visitor's model; the reply must be valid JSON."""
    text = "Aapko sharam nahi aati, padosiyon ko pata chalega to samajh aayega."
    try:
        raw, tokens = await chat(client, creds.model, _messages(CallContext(), [], text), creds)
    except _ERRORS as e:
        return {"ok": False, "message_user": plain_error(e), "tokens": 0}
    if parse_llm(raw) is None:
        return {"ok": False, "tokens": tokens, "message_user": "The model answered, but not with the JSON format the "
                "rule check needs. Try another model (results vary on models other than gpt-5.4-mini)."}
    return {"ok": True, "tokens": tokens,
            "message_user": f"Connected. The model replied with valid JSON ({tokens} tokens used)."}
