from pydantic import BaseModel


class Health(BaseModel):
    status: str
    version: str
    mode_capable: str  # "live" or "replay"
