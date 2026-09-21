"""Green tool: fetch a URL over HTTP(S) and return its text.

`web_search` finds pages; this reads one. That gap mattered in practice — a
search result is a title and a snippet, and answering from snippets is how a
research agent ends up confidently wrong about a page it never opened.

GET only, and the interesting part is what it refuses. A URL is model output,
and a model can be talked into a URL by any document it has read, so this tool
is the classic server-side request forgery surface: the agent runs *inside the
trust boundary*, and `http://169.254.169.254/` or `http://localhost:5432` are
reachable from here in a way they are not from the user's browser.

The defence is a resolve-then-check, applied to **every hop**:

1. The scheme must be http or https. No `file://`, `gopher://`, `ftp://`.
2. The hostname is resolved to its actual IP addresses, and every one of them
   must be a global unicast address. Loopback, link-local (which covers the
   cloud metadata endpoints), private ranges, multicast and reserved space are
   all refused.
3. Redirects are followed manually, one at a time, re-running the check on each
   new URL. Delegating redirects to the HTTP client would let a public host
   bounce us to `127.0.0.1` after the check had already passed — the standard
   way an allowlist that only validates the first URL is defeated.

Checking the resolved IP rather than the hostname is what makes this hold up:
a name that resolves to 127.0.0.1 is refused however innocuous it reads.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

MAX_RESPONSE_CHARS = 20_000
MAX_REDIRECTS = 3
REQUEST_TIMEOUT_SECONDS = 15.0

_ALLOWED_SCHEMES = frozenset({"http", "https"})


class HttpFetchError(RuntimeError):
    """The URL is refused, unreachable, or returned something unusable."""


def _addresses_for(
    hostname: str,
) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Every IP ``hostname`` resolves to, as address objects."""
    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise HttpFetchError(f"could not resolve host {hostname!r}") from exc

    addresses = []
    for info in infos:
        raw = info[4][0]
        try:
            addresses.append(ipaddress.ip_address(raw))
        except ValueError:
            continue
    if not addresses:
        raise HttpFetchError(f"host {hostname!r} resolved to no usable address")
    return addresses


def assert_public_url(url: str) -> None:
    """Raise unless ``url`` is http(s) and resolves only to public addresses."""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise HttpFetchError(
            f"{parsed.scheme or 'that'} URLs are not supported — http and https only"
        )
    hostname = parsed.hostname
    if not hostname:
        raise HttpFetchError("URL has no host")

    for address in _addresses_for(hostname):
        # is_global is the single check that covers loopback, private ranges,
        # link-local (169.254.169.254 and fe80::/10), multicast, reserved and
        # unspecified addresses. Enumerating them by hand always misses one.
        if not address.is_global:
            raise HttpFetchError(
                f"{hostname} resolves to {address}, which is not a public "
                "address. Internal and loopback addresses are refused."
            )


async def fetch(url: str) -> dict:
    """Fetch ``url``, validating every hop, and return the decoded body."""
    current = url.strip()
    if not current:
        raise HttpFetchError("url must not be empty")

    # follow_redirects=False: each hop is validated here before it is taken.
    async with httpx.AsyncClient(
        follow_redirects=False, timeout=REQUEST_TIMEOUT_SECONDS
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            assert_public_url(current)
            try:
                response = await client.get(
                    current, headers={"User-Agent": "GummyOS/1.0 (+local agent)"}
                )
            except httpx.HTTPError as exc:
                raise HttpFetchError(f"request failed: {type(exc).__name__}") from exc

            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise HttpFetchError("redirect without a Location header")
                current = str(response.url.join(location))
                continue

            text = response.text
            truncated = len(text) > MAX_RESPONSE_CHARS
            return {
                "url": str(response.url),
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "content": text[:MAX_RESPONSE_CHARS],
                "truncated": truncated,
                "ok": response.is_success,
            }

    raise HttpFetchError(f"more than {MAX_REDIRECTS} redirects")


async def execute(context: object, args: dict) -> dict:
    """Fetch ``args['url']``. No context is needed: nothing tenant-scoped."""
    return await fetch(str(args.get("url", "")))
