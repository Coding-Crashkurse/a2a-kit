"""Tests for webhook URL validation (anti-SSRF)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from a2akit.push.validation import validate_webhook_url

# Mock DNS resolution for tests — returns a public IP for any hostname.
_PUBLIC_ADDRINFO = [(2, 1, 6, "", ("93.184.216.34", 0))]


def _make_loop_mock(addrinfo):
    """Create a mock event loop whose getaddrinfo returns *addrinfo*."""
    loop = AsyncMock()
    loop.getaddrinfo = AsyncMock(return_value=addrinfo)
    return loop


def _loop_public():
    return _make_loop_mock(_PUBLIC_ADDRINFO)


def _loop_private():
    return _make_loop_mock([(2, 1, 6, "", ("127.0.0.1", 0))])


def _loop_fail():
    loop = AsyncMock()
    loop.getaddrinfo = AsyncMock(side_effect=OSError("DNS resolution failed"))
    return loop


@patch("a2akit.push.validation.asyncio.get_running_loop", _loop_public)
async def test_valid_https_url():
    assert await validate_webhook_url("https://example.com/webhook") is True


async def test_http_rejected_by_default():
    assert await validate_webhook_url("http://example.com/webhook") is False


@patch("a2akit.push.validation.asyncio.get_running_loop", _loop_public)
async def test_http_allowed_in_dev_mode():
    assert await validate_webhook_url("http://example.com/webhook", allow_http=True) is True


async def test_private_ip_10_x():
    assert await validate_webhook_url("https://10.0.0.1/webhook") is False


async def test_private_ip_172_16_x():
    assert await validate_webhook_url("https://172.16.0.1/webhook") is False


async def test_private_ip_192_168_x():
    assert await validate_webhook_url("https://192.168.1.1/webhook") is False


async def test_loopback_127_0_0_1():
    assert await validate_webhook_url("https://127.0.0.1/webhook") is False


async def test_loopback_ipv6():
    assert await validate_webhook_url("https://[::1]/webhook") is False


async def test_link_local_169_254():
    assert await validate_webhook_url("https://169.254.1.1/webhook") is False


async def test_public_ip():
    assert await validate_webhook_url("https://93.184.216.34/webhook") is True


@patch("a2akit.push.validation.asyncio.get_running_loop", _loop_public)
async def test_hostname():
    assert await validate_webhook_url("https://webhook.example.com/path") is True


async def test_no_scheme():
    assert await validate_webhook_url("example.com/webhook") is False


async def test_ftp_scheme():
    assert await validate_webhook_url("ftp://example.com/webhook") is False


async def test_empty_url():
    assert await validate_webhook_url("") is False


async def test_allowed_hosts_match():
    assert (
        await validate_webhook_url("https://allowed.com/webhook", allowed_hosts={"allowed.com"})
        is True
    )


async def test_allowed_hosts_no_match():
    assert (
        await validate_webhook_url("https://other.com/webhook", allowed_hosts={"allowed.com"})
        is False
    )


async def test_blocked_hosts_match():
    assert (
        await validate_webhook_url("https://blocked.com/webhook", blocked_hosts={"blocked.com"})
        is False
    )


async def test_private_ip_allowed_with_http():
    """Private IPs should still be blocked even with allow_http=True."""
    assert await validate_webhook_url("http://10.0.0.1/webhook", allow_http=True) is False


@patch("a2akit.push.validation.asyncio.get_running_loop", _loop_private)
async def test_ssrf_hostname_resolves_to_private_ip():
    """Hostname that resolves to a private IP must be blocked (SSRF)."""
    assert await validate_webhook_url("https://evil.attacker.com/webhook") is False


@patch("a2akit.push.validation.asyncio.get_running_loop", _loop_fail)
async def test_dns_resolution_failure_rejects():
    """Unresolvable hostnames must be rejected."""
    assert await validate_webhook_url("https://nonexistent.invalid/webhook") is False
