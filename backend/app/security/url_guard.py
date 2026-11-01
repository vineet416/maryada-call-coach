"""SSRF guard for the visitor-supplied LLM base URL: https only, public addresses only, resolved IP pinned for the connect."""
import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit

NAT64 = ipaddress.ip_network("64:ff9b::/96")
MAX_URL_LEN = 300


class UnsafeUrl(ValueError):
    """The message is safe to show to the visitor (it never contains the key)."""


@dataclass(frozen=True)
class SafeTarget:
    url: SplitResult  # the validated, normalised base URL
    host: str  # original hostname (Host header, TLS name)
    ip: str  # the one address we connect to
    port: int

    def pinned(self, path: str) -> str:
        """URL that connects straight to the validated IP (DNS is not consulted again)."""
        ip = f"[{self.ip}]" if ":" in self.ip else self.ip
        return f"https://{ip}:{self.port}{self.url.path.rstrip('/')}{path}"


def is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True only for globally routable unicast addresses (loopback, private, link-local, metadata, multicast, reserved: False)."""
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return is_public_ip(ip.ipv4_mapped)
        if ip.sixtofour is not None and not is_public_ip(ip.sixtofour):
            return False
        if ip.teredo is not None:
            return False
        if ip in NAT64:
            return is_public_ip(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))
    return ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_loopback or ip.is_link_local
                                 or ip.is_private or ip.is_unspecified or getattr(ip, "is_site_local", False))


def check_syntax(url: str) -> SplitResult:
    if not isinstance(url, str) or not url.strip() or len(url) > MAX_URL_LEN or any(c.isspace() or ord(c) < 32 for c in url):
        raise UnsafeUrl("Enter a valid base URL starting with https://")
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        raise UnsafeUrl("Enter a valid base URL starting with https://") from None
    if parts.scheme != "https":
        raise UnsafeUrl("The base URL must start with https://")
    if not parts.hostname:
        raise UnsafeUrl("Enter a valid base URL starting with https://")
    host = parts.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".localdomain")):
        raise UnsafeUrl("That base URL points to a private or internal address, which is not allowed.")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise UnsafeUrl("The base URL must not contain a username or password.")
    if parts.query or parts.fragment:
        raise UnsafeUrl("The base URL must not contain a query string or fragment.")
    if port is not None and not 1 <= port <= 65535:
        raise UnsafeUrl("Enter a valid base URL starting with https://")
    return parts


Resolver = Callable[[str, int], Awaitable[list[str]]]


async def system_resolver(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(loop.getaddrinfo(host, port, type=socket.SOCK_STREAM), 5)
    except (OSError, TimeoutError):
        raise UnsafeUrl("The base URL host could not be found.") from None
    return [i[4][0] for i in infos]


async def resolve_safe(url: str, resolver: Resolver | None = None) -> SafeTarget:
    """Validate the URL, resolve it, and refuse unless EVERY returned address is public. Returns the pinned target."""
    parts = check_syntax(url)
    host, port = parts.hostname or "", parts.port or 443
    try:
        literal = [str(ipaddress.ip_address(host.strip("[]")))]
    except ValueError:
        literal = None
    addrs = literal or await (resolver or system_resolver)(host, port)
    if not addrs:
        raise UnsafeUrl("The base URL host could not be found.")
    for a in addrs:
        try:
            ip = ipaddress.ip_address(a.split("%")[0])
        except ValueError:
            raise UnsafeUrl("The base URL host could not be resolved safely.") from None
        if not is_public_ip(ip):
            raise UnsafeUrl("That base URL points to a private or internal address, which is not allowed.")
    return SafeTarget(url=parts, host=host, ip=str(ipaddress.ip_address(addrs[0].split("%")[0])), port=port)
