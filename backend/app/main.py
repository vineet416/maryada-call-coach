import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.rest import router
from .config import log, settings
from .db import init_db
from .rules.loader import load_rules
from .security import redact

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")  # token usage etc.
for _name in ("", "uvicorn", "uvicorn.error", "uvicorn.access"):  # every handler scrubs keys from messages and tracebacks
    redact.install(logging.getLogger(_name).handlers)

BODY_LIMIT = 16 * 1024  # bytes, for the endpoints that carry keys
KEY_PATHS = ("/api/sessions", "/api/credentials/", "/api/llm/")


@asynccontextmanager
async def lifespan(_: FastAPI):
    redact.install(logging.getLogger().handlers + logging.getLogger("uvicorn").handlers
                   + logging.getLogger("uvicorn.error").handlers + logging.getLogger("uvicorn.access").handlers)
    init_db()
    load_rules()
    if settings.replay_only:
        log.warning("REPLAY_ONLY set: live calls are off")
    elif not settings.server_keys:
        log.info("No server keys: live calls need the visitor's own keys")
    yield


app = FastAPI(title="Maryada", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_origin_regex=r"http://localhost:\d+",
    allow_methods=["GET", "HEAD", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def limit_key_bodies(request: Request, call_next):
    if request.method == "POST" and request.url.path.startswith(KEY_PATHS):
        declared = request.headers.get("content-length")
        if declared is None or not declared.isdigit() or int(declared) > BODY_LIMIT:
            return JSONResponse({"detail": {"error": {"code": "too_large", "retryable": False,
                                                      "message_user": "That request is too large."}}}, status_code=413)
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def bad_request(_: Request, exc: RequestValidationError) -> JSONResponse:
    """The default 422 body echoes the submitted values (which can be keys): send field names only."""
    fields = sorted({".".join(str(p) for p in e["loc"][1:]) for e in exc.errors()})
    return JSONResponse({"detail": {"error": {"code": "bad_request", "retryable": False, "message_user":
                         "Some fields are missing or invalid: " + (", ".join(fields) or "request body") + "."}}}, status_code=422)


app.include_router(router)
