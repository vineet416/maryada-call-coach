"""One guarded HTTPS call to a visitor-supplied base URL: pinned public IP, no redirects, size cap, friendly errors."""
import json as _json

import httpx2 as httpx

from . import redact
from .url_guard import Resolver, UnsafeUrl, resolve_safe

MAX_BYTES = 1_000_000  # response size limit (1 MB)
TIMEOUT_S = 10.0


class ProviderError(Exception):
    """A failure from the visitor's provider; `message_user` is plain language and never contains the key."""

    def __init__(self, message_user: str, status: int | None = None, detail: str = "") -> None:
        super().__init__(message_user)
        self.message_user, self.status, self.detail = message_user, status, detail


def explain_status(status: int) -> str:
    if status in (401, 403):
        return f"The provider rejected the API key (HTTP {status}). Check the key and that it can use this model."
    if status == 404:
        return "The provider does not know this address or model (HTTP 404). Check the base URL and the model name."
    if status == 429:
        return "The provider says the rate limit or quota is used up (HTTP 429). Wait a little or use another key."
    if 300 <= status < 400:
        return "The provider answered with a redirect, which is not followed. Check the base URL."
    return f"The provider returned an error (HTTP {status})."


async def _error_detail(r: httpx.Response) -> str:
    """The provider's own error text (first 2 KB, shortened, key-scrubbed), or ''."""
    try:
        buf = bytearray()
        async for chunk in r.aiter_bytes():
            buf += chunk
            if len(buf) > 2048:
                break
        doc = _json.loads(bytes(buf))
        err = doc.get("error", doc) if isinstance(doc, dict) else {}
        msg = err.get("message") if isinstance(err, dict) else err
        return redact.redact(" ".join(str(msg).split()))[:160] if msg else ""
    except (ValueError, httpx.HTTPError, AttributeError):
        return ""


async def request(client: httpx.AsyncClient, base_url: str, path: str, api_key: str, *, method: str = "POST",
                  json: dict | None = None, timeout: float = TIMEOUT_S, max_bytes: int = MAX_BYTES,
                  resolver: Resolver | None = None) -> bytes:
    """Validate + resolve + pin, send, never follow redirects, read at most max_bytes. Raises UnsafeUrl / ProviderError."""
    target = await resolve_safe(base_url, resolver)  # re-resolved on every call; the IP checked here is the IP we connect to
    host_header = target.host if target.port == 443 else f"{target.host}:{target.port}"
    headers = {"Authorization": f"Bearer {api_key}", "Host": host_header, "Accept": "application/json"}
    try:
        async with client.stream(method, target.pinned(path), json=json, headers=headers, timeout=timeout,
                                 follow_redirects=False, extensions={"sni_hostname": target.host}) as r:
            if r.status_code != 200:
                detail = await _error_detail(r)
                raise ProviderError(explain_status(r.status_code) + (f" Provider says: {detail}" if detail else ""),
                                    r.status_code, detail)
            buf = bytearray()
            async for chunk in r.aiter_bytes():
                buf += chunk
                if len(buf) > max_bytes:
                    raise ProviderError("The provider's reply was too large and was dropped.")
            return bytes(buf)
    except httpx.TimeoutException:
        raise ProviderError("The provider did not answer in time.") from None
    except httpx.HTTPError as e:
        raise ProviderError(f"Could not reach the provider ({type(e).__name__}).") from None


__all__ = ["MAX_BYTES", "ProviderError", "UnsafeUrl", "request"]
