"""SSRF-safe outbound HTTP (SPEC §10).

Every user-supplied URL in HAYABUSA — a source feed, a webhook destination, an
EASM probe target — is fetched through this module and nothing else. The rule is
absolute because the attacker model is: an operator with `source:write` (or
anyone who can influence a URL field) tries to make the *server* issue a request
to `http://169.254.169.254/latest/meta-data/` or `http://localhost:6379`, using
HAYABUSA as a network proxy into infrastructure the attacker cannot otherwise
reach.

Four defences, all required — any one alone is bypassable:

1. **Scheme allowlist.** Only `http`/`https`. `file://`, `gopher://`, `ftp://`
   read local files or speak to text-based protocols in ways an HTTP client
   author never intended.
2. **Resolve, then validate the resolved IP** — not the hostname string.
   `evil.com` can resolve to `127.0.0.1`; blocking hostnames that "look
   private" (an `is_private_looking(str)` check) is trivially defeated by DNS.
3. **Connection pinned to the validated IP.** The request is sent to that exact
   address with the original hostname preserved only as the `Host` header and
   TLS SNI. Without pinning, the gap between "we resolved and checked" and "the
   HTTP client resolves again to actually connect" is a DNS-rebinding window: an
   attacker's nameserver returns a public IP for the check and a private one
   moments later for the real connection.
4. **Redirects re-validated at every hop, manually.** `httpx`'s automatic
   `follow_redirects` would happily land on a private IP after step 2 passed for
   the original URL — the check has to run again for the redirect target.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Final

import httpx

from app.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

ALLOWED_SCHEMES: Final = frozenset({"http", "https"})
MAX_REDIRECTS: Final = 5
DEFAULT_MAX_BODY_BYTES: Final = 20 * 1024 * 1024  # 20 MB — generous for a feed, not for an exfil

# Known cloud metadata endpoints. Mostly already covered by the generic
# link-local check below, but listed explicitly: metadata is the single highest
# value SSRF target (it hands over IAM credentials), so it gets a belt-and-braces
# check that survives even if the generic logic above it is ever loosened.
_METADATA_DENYLIST: Final = frozenset(
    {
        "169.254.169.254",  # AWS, GCP, Azure, Oracle Cloud, DigitalOcean
        "fd00:ec2::254",  # AWS IPv6
        "100.100.100.200",  # Alibaba Cloud
    }
)


class SSRFBlockedError(Exception):
    """A URL resolved to, or redirected to, an address that must not be reached."""

    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"Refusing to fetch {url!r}: {reason}")


class FetchTooLargeError(Exception):
    """The response exceeded the configured size cap."""


@dataclass(frozen=True)
class FetchResult:
    status_code: int
    headers: httpx.Headers
    body: bytes
    #: The URL actually fetched, after any redirects.
    final_url: str
    not_modified: bool


def is_public_address(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True only for an address it is safe to let HAYABUSA connect to.

    Denies private, loopback, link-local, multicast, reserved and unspecified
    ranges. An IPv4-mapped IPv6 address (`::ffff:127.0.0.1`) is unwrapped and the
    embedded IPv4 address is checked too — the wrapping is a well-known filter
    bypass technique, not a distinct address family.
    """
    if str(ip) in _METADATA_DENYLIST:
        return False

    if (
        isinstance(ip, ipaddress.IPv6Address)
        and ip.ipv4_mapped is not None
        and not is_public_address(ip.ipv4_mapped)
    ):
        return False

    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def resolve_public_address(host: str, port: int) -> str:
    """Resolve `host` and return one address, only if every resolved address is public.

    Rejecting on *any* private address in the result — not just picking a public
    one out of a mixed set — matters because some resolvers return a stable
    ordering; an attacker controlling DNS could otherwise put a public decoy
    first and a private target second, betting on which one a naive client uses.
    """
    if host.lower() in {"localhost", "localhost.localdomain"}:
        raise SSRFBlockedError(host, "localhost is not a permitted target")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None:
        if not is_public_address(literal):
            raise SSRFBlockedError(host, f"{host} is not a publicly routable address")
        return str(literal)

    try:
        import asyncio

        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SSRFBlockedError(host, f"DNS resolution failed: {exc}") from exc

    if not infos:
        raise SSRFBlockedError(host, "DNS resolution returned no addresses")

    resolved = {info[4][0] for info in infos}
    addresses = [ipaddress.ip_address(addr) for addr in resolved]

    blocked = [addr for addr in addresses if not is_public_address(addr)]
    if blocked:
        raise SSRFBlockedError(
            host, f"resolves to a non-public address ({blocked[0]}) — refusing all of {resolved}"
        )

    # Prefer IPv4: some environments have partial/broken IPv6 routing where a
    # connection to a technically-valid public IPv6 address simply hangs.
    addresses.sort(key=lambda addr: addr.version)
    return str(addresses[0])


async def safe_fetch(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    timeout_seconds: float | None = None,
) -> FetchResult:
    """Fetch a URL, enforcing every defence in the module docstring.

    Used by every source adapter (SPEC §3) and by the source "test" endpoint.
    Nothing else in the codebase should call `httpx` directly for a
    user-supplied URL.
    """
    settings = get_settings()
    timeout = httpx.Timeout(timeout_seconds or settings.http_timeout_seconds)
    request_headers = {"User-Agent": settings.http_user_agent, **(headers or {})}

    current_url = url
    redirects = 0

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        while True:
            parsed = httpx.URL(current_url)

            if parsed.scheme not in ALLOWED_SCHEMES:
                raise SSRFBlockedError(current_url, f"scheme {parsed.scheme!r} is not permitted")

            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            ip = await resolve_public_address(parsed.host, port)

            # Connect to the validated IP directly; the hostname travels only as
            # the Host header and the TLS SNI value, so virtual hosting and
            # certificate validation both still work. This is what closes the
            # DNS-rebinding gap described in the module docstring.
            pinned = parsed.copy_with(host=ip)
            request = client.build_request(method, pinned, headers=request_headers)
            request.headers["Host"] = parsed.host
            request.extensions["sni_hostname"] = parsed.host

            log.debug("safe_fetch_request", url=current_url, resolved_ip=ip, redirects=redirects)

            response = await client.send(request, stream=True)

            if response.is_redirect:
                await response.aclose()
                redirects += 1
                if redirects > MAX_REDIRECTS:
                    raise SSRFBlockedError(current_url, "too many redirects")

                location = response.headers.get("location")
                if not location:
                    raise SSRFBlockedError(current_url, "redirect with no Location header")

                # Resolve relative to the URL as the caller wrote it, not the
                # pinned IP form, so a relative redirect keeps the right host.
                current_url = str(httpx.URL(current_url).join(location))
                continue

            body = bytearray()
            try:
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > max_body_bytes:
                        raise FetchTooLargeError(
                            f"response exceeded {max_body_bytes} bytes from {current_url}"
                        )
            finally:
                await response.aclose()

            return FetchResult(
                status_code=response.status_code,
                headers=response.headers,
                body=bytes(body),
                final_url=current_url,
                not_modified=response.status_code == 304,
            )
