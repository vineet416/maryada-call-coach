"""Bring-your-own-keys: URL guard (SSRF), model-list cleaning, log redaction, cache bypass, start without keys."""
import asyncio
import io
import json
import logging
from pathlib import Path

import httpx2 as httpx
import pytest
from app import db
from app.api import rest
from app.config import settings
from app.main import bad_request
from app.rules import llm
from app.rules.schemas import CallContext
from app.security import redact, safe_http, url_guard
from app.security.credentials import Creds
from app.security.models_list import clean_models
from app.session import runner
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

FIX = Path(__file__).parent / "fixtures"
PUBLIC = "93.184.216.34"
KEY = "sk-test-SECRET-0123456789abcdef"
GKEY = "gnani-SECRET-9876543210fedcba"
GOOD_JSON = '{"findings":[],"good_practice":[]}'


def run(coro):
    return asyncio.run(coro)


def resolver_for(*ips):
    async def r(host, port):
        return list(ips)
    return r


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch):
    """Every hostname resolves to a public address unless a test says otherwise."""
    monkeypatch.setattr(url_guard, "system_resolver", resolver_for(PUBLIC))


# ------------------------------------------------------------------ SSRF guard
@pytest.mark.parametrize("url", [
    "http://api.example.com/v1",  # not https
    "https://localhost/v1",
    "https://127.0.0.1/v1",
    "https://10.1.2.3/v1",
    "https://192.168.1.10/v1",
    "https://172.16.0.5/v1",
    "https://169.254.169.254/latest/meta-data",  # cloud metadata
    "https://[::1]/v1",
    "https://[fe80::1]/v1",
    "https://[fc00::1]/v1",
    "https://[::ffff:127.0.0.1]/v1",  # IPv4-mapped loopback
    "https://[::ffff:10.0.0.1]/v1",
    "https://224.0.0.1/v1",  # multicast
    "https://0.0.0.0/v1",
    "https://240.0.0.1/v1",  # reserved
    "https://100.64.0.1/v1",  # carrier-grade NAT
    "https://user:pass@api.example.com/v1",  # credentials in the URL
    "https://api.example.com@evil.example.org/v1",
    "https://api.example.com/v1?key=abc",  # key-style query string
    "https://api.example.com/v1#frag",
    "ftp://api.example.com/v1",
    "javascript:alert(1)",
    "",
    "https://",
    "https://api.example.com:99999/v1",
])
def test_unsafe_urls_rejected(url):
    with pytest.raises(url_guard.UnsafeUrl):
        run(url_guard.resolve_safe(url))


def test_hostname_resolving_to_private_ip_rejected():
    for ip in ("10.0.0.7", "127.0.0.1", "169.254.169.254", "::1", "fd00::1"):
        with pytest.raises(url_guard.UnsafeUrl):
            run(url_guard.resolve_safe("https://llm.example.com/v1", resolver_for(ip)))


def test_one_private_address_among_public_ones_rejects():
    with pytest.raises(url_guard.UnsafeUrl):
        run(url_guard.resolve_safe("https://llm.example.com/v1", resolver_for(PUBLIC, "10.0.0.7")))


def test_public_https_accepted_and_pinned():
    t = run(url_guard.resolve_safe("https://api.groq.com/openai/v1"))
    assert t.ip == PUBLIC and t.host == "api.groq.com" and t.port == 443
    assert t.pinned("/models") == f"https://{PUBLIC}:443/openai/v1/models"


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_request_connects_to_the_validated_ip_with_original_host():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.url.host, req.headers["host"], req.extensions.get("sni_hostname")))
        return httpx.Response(200, json={"ok": True})

    async def go():
        async with _client(handler) as c:
            return await safe_http.request(c, "https://api.groq.com/openai/v1", "/models", KEY, method="GET")

    run(go())
    assert seen == [(PUBLIC, "api.groq.com", "api.groq.com")]


def test_dns_rebinding_second_lookup_private_is_rejected(monkeypatch):
    answers = iter([[PUBLIC], ["10.0.0.7"]])

    async def flip(host, port):
        return next(answers)

    monkeypatch.setattr(url_guard, "system_resolver", flip)
    calls = []

    async def go():
        async with _client(lambda r: calls.append(r) or httpx.Response(200, json={})) as c:
            await safe_http.request(c, "https://llm.example.com/v1", "/models", KEY, method="GET")  # lookup 1: fine
            with pytest.raises(url_guard.UnsafeUrl):
                await safe_http.request(c, "https://llm.example.com/v1", "/models", KEY, method="GET")  # lookup 2: private

    run(go())
    assert len(calls) == 1  # the second request never left


def test_redirect_to_private_ip_is_not_followed():
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data"})

    async def go():
        async with _client(handler) as c:
            with pytest.raises(safe_http.ProviderError) as e:
                await safe_http.request(c, "https://llm.example.com/v1", "/models", KEY, method="GET")
            return e.value

    err = run(go())
    assert len(calls) == 1 and "redirect" in err.message_user.lower()


def test_response_size_is_capped():
    def handler(req):
        return httpx.Response(200, content=b"x" * 2_000_000)

    async def go():
        async with _client(handler) as c:
            with pytest.raises(safe_http.ProviderError):
                await safe_http.request(c, "https://llm.example.com/v1", "/models", KEY, method="GET")

    run(go())


# ------------------------------------------------------------------ model list (recorded sample formats)
def _models(name):
    return clean_models((FIX / name).read_bytes())


def test_groq_models():
    m = _models("models_groq.json")
    assert m == ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "meta-llama/llama-4-scout-17b-16e-instruct",
                 "openai/gpt-oss-20b"]


def test_gemini_openai_models_strip_prefix():
    assert _models("models_gemini_openai.json") == ["gemini-2.0-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"]


def test_gemini_native_listing():
    assert _models("models_gemini_native.json") == ["gemini-2.0-flash", "gemini-2.5-flash"]


def test_openrouter_models_drop_non_text_output():
    assert _models("models_openrouter.json") == ["google/gemini-2.5-flash", "meta-llama/llama-3.3-70b-instruct:free",
                                                 "openai/gpt-4o-mini"]


def test_openai_models():
    assert _models("models_openai.json") == ["gpt-4.1", "gpt-4o-mini", "gpt-5.4-mini"]


def test_model_list_rejects_other_shapes():
    for bad in (b"not json", b'{"hello":1}', b"[1,2]"):
        with pytest.raises(ValueError):
            clean_models(bad)


# ------------------------------------------------------------------ cache bypass and visitor-only model
def _creds():
    return Creds(GKEY, "https://api.example-llm.com/v1", KEY, "my-model")


def _chat_json(content=GOOD_JSON):
    return {"choices": [{"message": {"content": content}}], "usage": {"total_tokens": 42}}


def test_visitor_session_never_reads_or_writes_the_shared_cache():
    c = _creds()
    ctx = CallContext()
    text = "Kal tak payment kar dijiye."
    msgs = llm._messages(ctx, [], text)
    k = llm.cache_key("my-model", c.base_url, msgs)
    poisoned = '{"findings":[{"rule_id":"R3","confidence":0.99,"quote":"x","reason":"x","rewrite":"x","kind":"violation"}],"good_practice":[]}'
    llm._CACHE.clear()
    llm._CACHE[k] = poisoned
    before = dict(llm._CACHE)
    hits = llm.STATS["cache_hits"]
    calls = []

    def handler(req):
        calls.append(json.loads(req.content)["model"])
        return httpx.Response(200, json=_chat_json())

    async def go():
        async with _client(handler) as client:
            return await llm.review(client, ctx, [], text, c)

    out, _ = run(go())
    c.wipe()
    assert calls == ["my-model"]  # the network was used, not the cache
    assert out is not None and out.findings == []
    assert llm._CACHE == before and llm.STATS["cache_hits"] == hits  # nothing read, nothing written
    llm._CACHE.clear()


def test_visitor_model_has_no_fallback_to_ours_and_error_is_reported():
    c = _creds()
    models, errors = [], []

    def handler(req):
        models.append(json.loads(req.content)["model"])
        return httpx.Response(401, json={"error": {"message": f"Incorrect API key provided: {KEY}"}})

    async def go():
        async with _client(handler) as client:
            return await llm.review(client, CallContext(), [], "Payment kijiye.", c, on_error=errors.append)

    out, _ = run(go())
    c.wipe()
    assert out is None and models == ["my-model"]
    assert errors and "rejected" in errors[0] and KEY not in errors[0]


def test_invalid_json_from_visitor_model_is_reported():
    c = _creds()
    errors = []

    async def go():
        async with _client(lambda r: httpx.Response(200, json=_chat_json("sorry, I cannot"))) as client:
            return await llm.review(client, CallContext(), [], "Payment kijiye.", c, on_error=errors.append)

    out, _ = run(go())
    c.wipe()
    assert out is None and errors == ["The language model did not reply with valid JSON."]


def test_llm_test_call_reports_tokens():
    c = _creds()
    reply = json.dumps({"findings": [], "good_practice": []})

    async def go():
        async with _client(lambda r: httpx.Response(200, json=_chat_json(reply))) as client:
            return await llm.test_call(client, c)

    res = run(go())
    c.wipe()
    assert res["ok"] is True and res["tokens"] == 42


def test_openai_new_model_parameters_are_adapted():
    c = _creds()
    bodies = []

    def handler(req):
        b = json.loads(req.content)
        bodies.append(b)
        if "max_tokens" in b:
            return httpx.Response(400, json={"error": {"message": "Unsupported parameter: 'max_tokens'. Use 'max_completion_tokens' instead."}})
        if "temperature" in b:
            return httpx.Response(400, json={"error": {"message": "Unsupported value: 'temperature' does not support 0."}})
        return httpx.Response(200, json=_chat_json())

    async def go():
        async with _client(handler) as client:
            return await llm.review(client, CallContext(), [], "Payment kijiye.", c)

    out, _ = run(go())
    c.wipe()
    assert out is not None and "max_completion_tokens" in bodies[-1] and "temperature" not in bodies[-1]


# ------------------------------------------------------------------ redaction
def test_redact_replaces_registered_keys_and_key_shaped_text():
    redact.register(KEY)
    try:
        out = redact.redact(f"boom {KEY} and Authorization: Bearer abcdef123456789 and x-api-key: zzzzzzzz9999")
    finally:
        redact.unregister(KEY)
    assert KEY not in out and "abcdef123456789" not in out and "zzzzzzzz9999" not in out


def test_unregistered_after_wipe():
    c = _creds()
    c.wipe()
    assert c.llm_key == "" and "SECRET" not in repr(c)


def test_filter_scrubs_message_and_traceback():
    redact.register(KEY)
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    redact.install([h])
    lg = logging.getLogger("test.redact")
    lg.addHandler(h)
    lg.propagate = False
    try:
        try:
            raise RuntimeError(f"provider echoed {KEY}")
        except RuntimeError:
            lg.exception("failed with %s", KEY)
    finally:
        redact.unregister(KEY)
        lg.removeHandler(h)
    assert buf.getvalue() and KEY not in buf.getvalue()


def test_no_key_in_logs_on_error_paths(caplog, monkeypatch, tmp_path):
    """Provider 401 echoing the key, a crash whose message holds the key, and a 422: nothing reaches logs or responses."""
    redact.install([caplog.handler])  # the same filter main.py puts on every handler
    caplog.set_level(logging.DEBUG)
    c = Creds(GKEY, "https://api.example-llm.com/v1", KEY, "my-model")

    async def provider_error():
        def handler(req):
            return httpx.Response(401, json={"error": {"message": f"Incorrect API key provided: {KEY}"}})
        async with _client(handler) as client:
            await llm.review(client, CallContext(), [], "Payment kijiye.", c)
            return await llm.test_call(client, c)

    res = run(provider_error())
    assert KEY not in json.dumps(res)

    # a crash inside the live run whose exception text contains both keys
    monkeypatch.setattr(settings, "db_path", tmp_path / "t.db")
    db.init_db()

    async def boom(s):
        raise RuntimeError(f"unexpected {s.creds.llm_key} / {s.creds.gnani_key}")

    monkeypatch.setattr(runner, "_run_live", boom)

    async def crash():
        s = runner.new_session("c06", "live", c)
        runner.start(s)
        await s.task
        return s

    s = run(crash())
    events = json.dumps(s.log.events)
    assert KEY not in events and GKEY not in events
    assert s.creds is None  # wiped when the session ended

    # a 422 for a bad body must not echo what was submitted
    with pytest.raises(ValidationError) as ve:
        rest.StartBody(scenario_id="c06", credentials={"gnani": {"api_key": GKEY}, "llm": {"base_url": 5, "api_key": KEY}})
    resp = run(bad_request(None, RequestValidationError(ve.value.errors())))
    assert KEY.encode() not in resp.body and GKEY.encode() not in resp.body
    assert KEY not in caplog.text and GKEY not in caplog.text
    assert any("failed" in r.getMessage() for r in caplog.records)  # the error path really logged


# ------------------------------------------------------------------ start without keys, replay without keys
def test_live_start_without_keys_is_rejected_and_replay_works(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "db_path", tmp_path / "t.db")
    monkeypatch.setattr(settings, "server_keys_enabled", False)
    monkeypatch.setattr(settings, "euri_api_key", "")
    monkeypatch.setattr(settings, "gnani_api_key_id", "")
    db.init_db()
    with pytest.raises(HTTPException) as e:
        run(rest.create_session(rest.StartBody(scenario_id="c06", mode="live")))
    assert e.value.status_code == 400 and e.value.detail["error"]["code"] == "keys_required"

    out = run(rest.create_session(rest.StartBody(scenario_id="c06", mode="replay")))
    assert out["effective_mode"] == "replay"


def test_server_env_keys_are_ignored_when_server_keys_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "db_path", tmp_path / "t.db")
    monkeypatch.setattr(settings, "server_keys_enabled", False)
    monkeypatch.setattr(settings, "euri_api_key", "env-llm-key-123456")
    monkeypatch.setattr(settings, "gnani_api_key_id", "env-gnani-key-123456")
    db.init_db()
    assert settings.server_keys is False
    with pytest.raises(HTTPException) as e:
        run(rest.create_session(rest.StartBody(scenario_id="c06", mode="live")))
    assert e.value.detail["error"]["code"] == "keys_required"
    out, _ = run(llm.review(None, CallContext(), [], "Payment kijiye."))  # no client needed: refused before any call
    assert out is None


def test_live_start_with_unsafe_base_url_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "db_path", tmp_path / "t.db")
    db.init_db()
    body = rest.StartBody(scenario_id="c06", mode="live", credentials={
        "gnani": {"api_key": GKEY}, "llm": {"base_url": "https://127.0.0.1/v1", "api_key": KEY, "model": "m"}})
    with pytest.raises(HTTPException) as e:
        run(rest.create_session(body))
    assert e.value.detail["error"]["code"] == "invalid_base_url"


def test_concurrent_live_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "db_path", tmp_path / "t.db")
    monkeypatch.setattr(settings, "max_live_sessions", 3)
    db.init_db()
    monkeypatch.setattr(runner, "_live_active", {"a", "b", "c"})
    monkeypatch.setattr(runner, "SESSIONS", {})

    async def go():
        c = _creds()
        s = runner.new_session("c06", "live", c)
        return s, c

    s, c = run(go())
    assert s.effective_mode == "replay" and "busy" in s.reason and s.creds is None and c.llm_key == ""


def test_filter_keeps_args_usable_for_uvicorn_style_formatters():
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "f", 1, '%s - "%s %s HTTP/%s" %d',
                            ("127.0.0.1:1", "POST", "/api/sessions", "1.1", 200), None)
    assert redact.RedactFilter().filter(rec)
    _client, method, _path, _ver, status = rec.args  # uvicorn unpacks the args itself
    assert (method, status) == ("POST", 200) and rec.getMessage().endswith("200")
