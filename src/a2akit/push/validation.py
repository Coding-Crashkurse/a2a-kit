"""Webhook URL validation (anti-SSRF)."""

from __future__ import annotations

import ipaddress
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_BLOCKED_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def validate_webhook_url(
    url: str,
    *,
    allow_http: bool = False,
    allowed_hosts: set[str] | None = None,
    blocked_hosts: set[str] | None = None,
) -> bool:
    """Validate a webhook URL for safety.

    Checks:
    1. Scheme is https (unless allow_http for dev)
    2. No private/loopback IP addresses
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
    if allowed_hosts and hostname.lower() not in allowed_hosts:
        return False

    try:
        ip = ipaddress.ip_address(hostname)
        for blocked in _BLOCKED_RANGES:
            if ip in blocked:
                return False
    except ValueError:
        pass  # Hostname, not IP - that's fine

    return True
