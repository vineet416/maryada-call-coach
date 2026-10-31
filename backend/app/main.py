import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.rest import router
from .config import log, settings
from .db import init_db
from .rules.loader import load_rules

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")  # token usage etc.


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    load_rules()
    if not settings.live_capable:
        log.warning("Live keys missing or REPLAY_ONLY set: starting in replay-only mode")
    yield


app = FastAPI(title="Maryada", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_origin_regex=r"http://localhost:\d+",
    allow_methods=["GET", "HEAD", "POST"],
    allow_headers=["*"],
)
app.include_router(router)
