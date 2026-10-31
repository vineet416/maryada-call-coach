"""LLM review of one agent turn via Euri (OpenAI-compatible), using the shared httpx2 client."""
import asyncio
import logging
import time

import httpx2 as httpx

from ..config import settings
from .engine import parse_llm
from .loader import load_rules
from .schemas import CallContext, LlmOut, Turn

log = logging.getLogger("maryada.rules.llm")

LATE_TIMEOUT_S = 8.0  # total budget for one review, fallback attempt included; the pipeline decides when to show "late"
MIN_WORDS = 4  # docs/13 §4.1: skip the LLM for segments under 4 words

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


async def _ask(client: httpx.AsyncClient, model: str, ctx: CallContext, history: list[Turn], text: str,
               api_key: str, base_url: str) -> str:
    body = {"model": model, "temperature": 0, "max_tokens": 250, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system_prompt()},
                         {"role": "user", "content": user_prompt(ctx, history, text)}]}
    url, headers = base_url.rstrip("/") + "/chat/completions", {"Authorization": f"Bearer {api_key}"}
    try:
        r = await client.post(url, json=body, headers=headers)
    except (httpx.RemoteProtocolError, httpx.LocalProtocolError):
        if not settings.llm_http2:
            raise
        log.warning("llm http2 negotiation failed, retrying over HTTP/1.1")
        async with httpx.AsyncClient(timeout=LATE_TIMEOUT_S, http2=False) as h1:
            r = await h1.post(url, json=body, headers=headers)
    r.raise_for_status()
    j = r.json()
    u = j.get("usage") or {}
    log.info("llm tokens model=%s prompt=%s completion=%s total=%s", model, u.get("prompt_tokens"),
             u.get("completion_tokens"), u.get("total_tokens"))
    return j["choices"][0]["message"]["content"]


async def review(client: httpx.AsyncClient, ctx: CallContext, history: list[Turn], text: str,
                 api_key: str | None = None, base_url: str | None = None) -> tuple[LlmOut | None, int]:
    """Returns (validated result or None when degraded, llm_ms). Invalid/failed -> one retry with the fallback model."""
    if len(text.split()) < MIN_WORDS:
        return LlmOut(), 0
    key, url = api_key or settings.euri_api_key, base_url or settings.euri_base_url
    t0 = time.perf_counter()
    for model in (settings.llm_model, settings.llm_fallback_model):
        try:
            left = LATE_TIMEOUT_S - (time.perf_counter() - t0)
            if left <= 0:
                break
            raw = await asyncio.wait_for(_ask(client, model, ctx, history, text, key, url), left)
        except (TimeoutError, httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            log.warning("llm call failed model=%s err=%s", model, type(e).__name__)
            continue
        out = parse_llm(raw)
        if out is not None:
            return out, int((time.perf_counter() - t0) * 1000)
        log.warning("llm json invalid model=%s", model)
    return None, int((time.perf_counter() - t0) * 1000)  # caller: prefilter only + banner llm_degraded


async def warm_up(client: httpx.AsyncClient, api_key: str | None = None, base_url: str | None = None) -> bool:
    """Tiny request at session start: opens the connection and validates the key."""
    try:
        await _ask(client, settings.llm_model, CallContext(), [], "Namaste, main Rohit bol raha hoon.",
                   api_key or settings.euri_api_key, base_url or settings.euri_base_url)
        return True
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        return False
