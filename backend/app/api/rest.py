from fastapi import APIRouter

from ..config import settings
from ..models import Health

VERSION = "0.1.0"
router = APIRouter()


@router.api_route("/health", methods=["GET", "HEAD"], response_model=Health)
def health() -> Health:
    mode = "live" if settings.live_capable else "replay"
    return Health(status="ok", version=VERSION, mode_capable=mode)
