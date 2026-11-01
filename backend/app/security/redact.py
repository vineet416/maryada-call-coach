"""Log redaction: keys live in memory for one session; any text that reaches a log handler is scrubbed first."""
import logging
import re
import threading

_lock = threading.Lock()
_secrets: dict[str, int] = {}  # secret value -> reference count (a key is registered while a session or request uses it)
MIN_LEN = 6  # shorter values are not treated as keys (they would blank ordinary words)

_PATTERNS = [
    re.compile(r"(?i)\b(authorization|x-api-key[\w-]*|api[_-]?key)(\s*[:=]\s*)(bearer\s+)?[^\s,;'\"}]+"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\b(sk|gsk|AIza|or)[-_][A-Za-z0-9_-]{12,}"),
]
MASK = "[redacted]"


def register(secret: str) -> None:
    if len(secret) >= MIN_LEN:
        with _lock:
            _secrets[secret] = _secrets.get(secret, 0) + 1


def unregister(secret: str) -> None:
    with _lock:
        n = _secrets.get(secret, 0)
        if n <= 1:
            _secrets.pop(secret, None)
        else:
            _secrets[secret] = n - 1


def redact(text: str) -> str:
    with _lock:
        known = sorted(_secrets, key=len, reverse=True)
    for s in known:
        text = text.replace(s, MASK)
    text = _PATTERNS[0].sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", text)
    for p in _PATTERNS[1:]:
        text = p.sub(MASK, text)
    return text


class RedactFilter(logging.Filter):
    """Handler filter: rewrites the message and the formatted traceback so no key reaches any output."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Keep msg/args as a pair (uvicorn's formatter unpacks args): scrub each part instead of pre-formatting.
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        else:
            record.msg, record.args = redact(record.getMessage()), ()
        if isinstance(record.args, tuple):
            record.args = tuple(a if isinstance(a, int | float | bool | type(None)) else redact(str(a)) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: (v if isinstance(v, int | float | bool | type(None)) else redact(str(v))) for k, v in record.args.items()}
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        if record.stack_info:
            record.stack_info = redact(record.stack_info)
        return True


def install(handlers: list[logging.Handler]) -> None:
    for h in handlers:
        if not any(isinstance(f, RedactFilter) for f in h.filters):
            h.addFilter(RedactFilter())
