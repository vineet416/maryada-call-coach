import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import db
from ..config import settings
from ..models import Health
from ..session import assets, runner

VERSION = "0.1.0"
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


class StartBody(BaseModel):
    scenario_id: str
    mode: str = "live"


@router.post("/api/sessions")
def create_session(body: StartBody) -> dict:
    if body.scenario_id not in assets.scenarios():
        raise _err(404, "unknown_scenario", "That case does not exist.")
    s = runner.new_session(body.scenario_id, body.mode)
    out = {"session_id": s.id, "effective_mode": s.effective_mode, "ws_url": f"/ws/session/{s.id}"}
    if s.reason:
        out["reason"] = s.reason
    return out


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
        await ws.send_json({"seq": 0, "type": "error", "t_ms": 0, "data": {
            "code": "unknown_session", "message_user": "That session does not exist.", "retryable": False}})
        await ws.close()
        return
    try:
        first = await ws.receive_json()  # {"type":"start"} or {"type":"resume","last_seq":N}
        last_seq = int(first.get("last_seq", 0)) if first.get("type") == "resume" else 0
    except WebSocketDisconnect:
        return
    except (ValueError, TypeError, AttributeError):  # not JSON, not an object, or a bad last_seq
        await ws.close(code=1003)
        return
    runner.start(s)

    async def listen() -> None:
        try:
            while True:
                if (await ws.receive_json()).get("type") == "stop":
                    runner.stop(s)
        except (WebSocketDisconnect, RuntimeError, ValueError, TypeError, AttributeError):
            return

    listener = asyncio.create_task(listen())
    try:
        async for env in s.log.follow(last_seq):
            await ws.send_json(env)
    except WebSocketDisconnect:
        pass
    finally:
        listener.cancel()
        try:
            await ws.close()
        except RuntimeError:
            pass
