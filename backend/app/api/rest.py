import asyncio
import time
from collections import deque
from pathlib import Path
from typing import Literal

import httpx2 as httpx
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, SecretStr

from .. import db
from ..config import log, settings
from ..models import Health
from ..rules import llm
from ..rules.loader import load_rules
from ..security import redact, safe_http
from ..security.credentials import CredentialsIn, Creds
from ..security.models_list import clean_models
from ..security.url_guard import UnsafeUrl, resolve_safe
from ..session import assets, runner
from ..stt import realtime
from ..stt.base import SttAuthError, SttError

VERSION = "0.1.0"
KEYS_MSG = "Add your Gnani key and your language model details in Settings to start a live call, or play the recorded run."
router = APIRouter()


def _err(status: int, code: str, message: str, retryable: bool = False) -> HTTPException:
    return HTTPException(status, {"error": {"code": code, "message_user": message, "retryable": retryable}})


@router.api_route("/health", methods=["GET", "HEAD"], response_model=Health)
def health() -> Health:
    mode = "live" if settings.live_capable else "replay"
    return Health(status="ok", version=VERSION, mode_capable=mode)


@router.get("/api/scenarios")
def list_scenarios() -> list[dict]:
    man = assets.audio_manifest()
    return [{"id": sc["id"], "title": sc["title"], "summary": sc["summary"], "hero": sc.get("hero", False),
             "duration_s": round(man[sid]["duration_ms"] / 1000) if sid in man else None,
             "tags": sorted({lab[0] for t in sc["turns"] for lab in t.get("L", [])})}
            for sid, sc in assets.scenarios().items()]


@router.get("/api/scenarios/{sid}")
def get_scenario(sid: str) -> dict:
    """Case meta and the call-audio timeline for the waveform; no labels and no script text."""
    sc = assets.scenarios().get(sid)
    if sc is None:
        raise _err(404, "unknown_scenario", "That case does not exist.")
    entry = assets.audio_manifest().get(sid)
    turns = [{"idx": t["idx"], "speaker": assets.SPEAKER.get(t["speaker"], t["speaker"]),
              "offset_ms": t["offset_ms"], "duration_ms": t["duration_ms"], "audio_url": f"/audio/{t['mp3']}"} for t in entry["turns"]] if entry else []
    return {"id": sid, "title": sc["title"], "summary": sc["summary"], "hero": sc.get("hero", False),
            "simulated_start_time": sc.get("time"), "turns": turns,
            "call_audio_url": f"/audio/{entry['call_mp3']}" if entry else None,
            "duration_ms": entry["duration_ms"] if entry else None}


@router.get("/api/rules")
def list_rules() -> list[dict]:
    keys = ("id", "title", "kind_default", "rbi_ref", "summary", "why", "examples_bad", "examples_good")
    return [{k: r.get(k) for k in keys} for r in load_rules()["rules"]]


class StartBody(BaseModel):
    scenario_id: str
    mode: str = "live"
    credentials: CredentialsIn | None = None  # the visitor's keys; sent in the POST body only, never in a URL
    pause_for_coach: bool = False  # the user's option: the call pauses only while a coach clip plays


class TestBody(BaseModel):
    kind: Literal["gnani", "llm"]
    api_key: SecretStr = Field(max_length=300)
    base_url: str = Field("", max_length=300)  # llm only
    model: str = Field("", max_length=120)  # llm only


class ModelsBody(BaseModel):
    base_url: str = Field(max_length=300)
    api_key: SecretStr = Field(max_length=300)


_calls: deque[float] = deque()  # global rate limit for the key-check endpoints: 10 per minute
RATE_PER_MIN = 10


def _rate_limit() -> None:
    now = time.monotonic()
    while _calls and now - _calls[0] > 60:
        _calls.popleft()
    if len(_calls) >= RATE_PER_MIN:
        raise _err(429, "rate_limited", "Too many checks in a minute. Wait a little and try again.", True)
    _calls.append(now)


async def _checked_url(url: str) -> None:
    try:
        await resolve_safe(url)
    except UnsafeUrl as e:
        raise _err(400, "invalid_base_url", str(e)) from None


@router.post("/api/sessions")
async def create_session(body: StartBody) -> dict:
    if body.scenario_id not in assets.scenarios():
        raise _err(404, "unknown_scenario", "That case does not exist.")
    creds = None
    if body.mode == "live":
        if body.credentials is not None:
            c = body.credentials
            if not c.gnani.api_key.get_secret_value().strip() or not c.llm.api_key.get_secret_value().strip() \
                    or not c.llm.base_url.strip() or not c.llm.model.strip():
                raise _err(400, "keys_required", KEYS_MSG)
            await _checked_url(c.llm.base_url.strip())
            creds = Creds.from_body(c)
        elif not settings.server_keys:
            raise _err(400, "keys_required", KEYS_MSG)
    s = runner.new_session(body.scenario_id, body.mode, creds, body.pause_for_coach)
    out = {"session_id": s.id, "effective_mode": s.effective_mode, "ws_url": f"/ws/session/{s.id}"}
    if s.reason:
        out["reason"] = s.reason
    return out


@router.post("/api/llm/models")
async def llm_models(body: ModelsBody) -> dict:
    """The provider's chat models for the Settings dropdown (browsers cannot call most providers: CORS)."""
    _rate_limit()
    key = body.api_key.get_secret_value().strip()
    if not key:
        raise _err(400, "keys_required", "Enter the API key first.")
    redact.register(key)
    try:
        async with httpx.AsyncClient() as client:
            raw = await safe_http.request(client, body.base_url.strip(), "/models", key, method="GET")
        models = clean_models(raw)
    except UnsafeUrl as e:
        raise _err(400, "invalid_base_url", str(e)) from None
    except safe_http.ProviderError as e:
        raise _err(502, "provider_error", e.message_user, True) from None
    except ValueError:
        raise _err(502, "provider_error", "The provider did not return a model list in the expected format.") from None
    finally:
        redact.unregister(key)
    return {"models": models}


@router.post("/api/credentials/test")
async def test_credentials(body: TestBody) -> dict:
    """Gnani: opens the speech WebSocket with the key and waits for 'connected' (no audio sent). LLM: one short
    sample classification, checked for valid JSON, with the tokens used."""
    _rate_limit()
    key = body.api_key.get_secret_value().strip()
    if not key:
        raise _err(400, "keys_required", "Enter the API key first.")
    redact.register(key)
    try:
        if body.kind == "gnani":
            try:
                await realtime.check_key(key)
            except SttAuthError:
                return {"ok": False, "message_user": "Gnani rejected this key. Check it and try again."}
            except SttError:
                return {"ok": False, "message_user": "Could not reach the Gnani speech service. Try again in a moment."}
            return {"ok": True, "message_user": "Connected. Gnani accepted the key (no audio was sent)."}
        if not body.base_url.strip() or not body.model.strip():
            raise _err(400, "keys_required", "Enter the base URL and a model first.")
        await _checked_url(body.base_url.strip())
        creds = Creds(key, body.base_url.strip(), key, body.model.strip())
        try:
            async with httpx.AsyncClient() as client:
                return await llm.test_call(client, creds)
        finally:
            creds.wipe()
    finally:
        redact.unregister(key)


@router.get("/api/sessions/{sid}")
def get_session(sid: str) -> dict:
    out = db.session_summary(sid)
    if out is None:
        raise _err(404, "unknown_session", "That session does not exist.")
    return out


@router.get("/audio/{path:path}")
def audio(path: str) -> FileResponse:
    """Call-turn and coach MP3s only (never the raw or cached files)."""
    root = assets.audio_dir().resolve()
    p = (root / path).resolve()
    if p.suffix != ".mp3" or root not in p.parents or p.relative_to(root).parts[0].startswith(("_", "raw")):
        raise _err(404, "not_found", "Audio not found.")
    if not p.is_file():
        raise _err(404, "not_found", "Audio not found.")
    return FileResponse(Path(p), media_type="audio/mpeg")


@router.websocket("/ws/session/{sid}")
async def ws_session(ws: WebSocket, sid: str) -> None:
    s = runner.SESSIONS.get(sid)
    await ws.accept()
    if s is None:
        log.info("ws unknown session=%r", sid)
        await ws.send_json({"seq": 0, "type": "error", "t_ms": 0, "data": {
            "code": "unknown_session", "message_user": "That session does not exist.", "retryable": False}})
        await ws.close()
        return
    opened = time.monotonic()
    sent = 0  # events sent on this connection
    last_sent = 0  # seq of the last event sent
    first_kind = "start"
    # close code as seen by the server (1006 = no close frame, 1011 = uvicorn ping timeout, 1001/1000 = browser left)
    close_code, close_by = None, "server"
    log.info("ws connect session=%r", sid)
    try:
        first = await ws.receive_json()  # {"type":"start"} or {"type":"resume","last_seq":N}
        last_seq = int(first.get("last_seq", 0)) if first.get("type") == "resume" else 0
        first_kind = "resume" if first.get("type") == "resume" else "start"
    except WebSocketDisconnect as e:
        log.info("ws disconnect session=%r code=%s by=transport before=start duration_s=%.1f", sid, e.code, time.monotonic() - opened)
        return
    except RuntimeError:
        return
    except (ValueError, TypeError, AttributeError):  # not JSON, not an object, or a bad last_seq
        await ws.close(code=1003)
        log.info("ws disconnect session=%r code=1003 by=server reason=bad_first_message duration_s=%.1f", sid, time.monotonic() - opened)
        return
    if first_kind == "resume":
        total = len(s.log.events)
        log.info("ws resume session=%r from_last_seq=%d events_to_replay=%d", sid, last_seq, max(0, total - last_seq))
    runner.start(s)

    async def listen() -> None:
        nonlocal close_code, close_by
        try:
            while True:
                if (await ws.receive_json()).get("type") == "stop":
                    runner.stop(s)
        except WebSocketDisconnect as e:
            close_code, close_by = e.code, "transport"
        except (RuntimeError, ValueError, TypeError, AttributeError):
            return

    async def send() -> None:
        nonlocal sent, last_sent, close_code, close_by
        try:
            async for env in s.log.follow(last_seq):
                await ws.send_json(env)
                sent += 1
                last_sent = env.get("seq", last_sent)
        except WebSocketDisconnect as e:
            close_code, close_by = e.code, "transport"
        except (RuntimeError, OSError) as e:  # a failed send: report the cause, then end quietly
            close_by = "send_error:" + type(e).__name__

    listener = asyncio.create_task(listen())
    sender = asyncio.create_task(send())
    try:
        await asyncio.wait({listener, sender}, return_when=asyncio.FIRST_COMPLETED)
        if not sender.done() and close_code is None:  # the listener ended on a bad message only: keep streaming
            await sender
    finally:
        listener.cancel()
        sender.cancel()
        finished = s.log.done and close_by == "server"
        try:
            await ws.close()
        except RuntimeError:
            pass
        log.info("ws disconnect session=%r code=%s by=%s ended=%s duration_s=%.1f last_seq_sent=%d events_sent=%d",
                 sid, close_code if close_code is not None else (1000 if finished else "none"), close_by, finished,
                 time.monotonic() - opened, last_sent, sent)
