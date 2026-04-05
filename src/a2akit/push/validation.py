"""Webhook URL validation (anti-SSRF)."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check whether an IP address is unsafe to reach from the server.

    Uses Python's own ``is_global`` classification (maintained against the
    IANA special-purpose address registries) rather than a hand-maintained
    allow/deny list. This automatically rejects:

    - Loopback (127.0.0.0/8, ::1)
    - Private (RFC 1918, RFC 4193 ULA)
    - Link-local (169.254.0.0/16, fe80::/10)
    - Reserved / unspecified (notably ``0.0.0.0``, which Linux/macOS
      silently route to localhost — a classic SSRF bypass vector)
    - Shared address space, benchmarking, documentation, multicast, etc.

    IPv4-mapped IPv6 addresses (``::ffff:a.b.c.d``) are unwrapped first so
    that an attacker cannot smuggle a private IPv4 through an IPv6 literal.
    """
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return not ip.is_global


async def validate_webhook_url(
    url: str,
    *,
    allow_http: bool = False,
    allowed_hosts: set[str] | None = None,
    blocked_hosts: set[str] | None = None,
) -> bool:
    """Validate a webhook URL for safety.

    Checks:
    1. Scheme is https (unless allow_http for dev)
    2. No private/loopback IP addresses (resolved via DNS)
    3. No blocked hostnames
    4. Optional allowlist enforcement
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if not allow_http and parsed.scheme != "https":
        return False
    if allow_http and parsed.scheme == "http":
        logger.warning(
            "Allowing insecure HTTP webhook URL %r — do NOT use in production (A2A §4.1)",
            url,
        )
    if parsed.scheme not in ("http", "https"):
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    if blocked_hosts and hostname.lower() in blocked_hosts:
        return False
    if allowed_hosts:
        # Allowlist mode: skip DNS resolution — the operator explicitly trusts these hosts.
        return hostname.lower() in allowed_hosts

    # Check IP literals directly
    try:
        ip = ipaddress.ip_address(hostname)
        return not _is_blocked_ip(ip)
    except ValueError:
        pass  # Not an IP literal — resolve via DNS below

    # Async DNS resolution to prevent SSRF via hostname → private IP.
    # Uses the event-loop's getaddrinfo to avoid blocking the loop.
    loop = asyncio.get_running_loop()
    try:
        addrinfo = await loop.getaddrinfo(hostname, None, proto=0)
    except OSError:
        logger.warning("DNS resolution failed for webhook host %r", hostname)
        return False

    for _family, _type, _proto, _canonname, sockaddr in addrinfo:
        ip = ipaddress.ip_address(sockaddr[0])
        if _is_blocked_ip(ip):
            logger.warning(
                "Webhook host %r resolves to blocked IP %s (SSRF protection)",
                hostname,
                ip,
            )
            return False

    return True
