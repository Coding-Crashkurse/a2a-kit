"""Tests for webhook URL validation (anti-SSRF)."""

from __future__ import annotations

import socket
from unittest.mock import patch

from a2akit.push.validation import validate_webhook_url

# Mock DNS resolution for tests — returns a public IP for any hostname.
_PUBLIC_ADDRINFO = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]


def _fake_getaddrinfo_public(*args, **kwargs):
    return _PUBLIC_ADDRINFO


def _fake_getaddrinfo_private(*args, **kwargs):
    """Simulate a hostname that resolves to a private IP (SSRF attack)."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]


def _fake_getaddrinfo_fail(*args, **kwargs):
    raise socket.gaierror("DNS resolution failed")


@patch("a2akit.push.validation.socket.getaddrinfo", _fake_getaddrinfo_public)
def test_valid_https_url():
    assert validate_webhook_url("https://example.com/webhook") is True


def test_http_rejected_by_default():
    assert validate_webhook_url("http://example.com/webhook") is False


@patch("a2akit.push.validation.socket.getaddrinfo", _fake_getaddrinfo_public)
def test_http_allowed_in_dev_mode():
    assert validate_webhook_url("http://example.com/webhook", allow_http=True) is True


def test_private_ip_10_x():
    assert validate_webhook_url("https://10.0.0.1/webhook") is False


def test_private_ip_172_16_x():
    assert validate_webhook_url("https://172.16.0.1/webhook") is False


def test_private_ip_192_168_x():
    assert validate_webhook_url("https://192.168.1.1/webhook") is False


def test_loopback_127_0_0_1():
    assert validate_webhook_url("https://127.0.0.1/webhook") is False


def test_loopback_ipv6():
    assert validate_webhook_url("https://[::1]/webhook") is False


def test_link_local_169_254():
    assert validate_webhook_url("https://169.254.1.1/webhook") is False


def test_public_ip():
    assert validate_webhook_url("https://93.184.216.34/webhook") is True


@patch("a2akit.push.validation.socket.getaddrinfo", _fake_getaddrinfo_public)
def test_hostname():
    assert validate_webhook_url("https://webhook.example.com/path") is True


def test_no_scheme():
    assert validate_webhook_url("example.com/webhook") is False


def test_ftp_scheme():
    assert validate_webhook_url("ftp://example.com/webhook") is False


def test_empty_url():
    assert validate_webhook_url("") is False


def test_allowed_hosts_match():
    assert (
        validate_webhook_url("https://allowed.com/webhook", allowed_hosts={"allowed.com"}) is True
    )


def test_allowed_hosts_no_match():
    assert (
        validate_webhook_url("https://other.com/webhook", allowed_hosts={"allowed.com"}) is False
    )


def test_blocked_hosts_match():
    assert (
        validate_webhook_url("https://blocked.com/webhook", blocked_hosts={"blocked.com"}) is False
    )


def test_private_ip_allowed_with_http():
    """Private IPs should still be blocked even with allow_http=True."""
    assert validate_webhook_url("http://10.0.0.1/webhook", allow_http=True) is False


@patch("a2akit.push.validation.socket.getaddrinfo", _fake_getaddrinfo_private)
def test_ssrf_hostname_resolves_to_private_ip():
    """Hostname that resolves to a private IP must be blocked (SSRF)."""
    assert validate_webhook_url("https://evil.attacker.com/webhook") is False


@patch("a2akit.push.validation.socket.getaddrinfo", _fake_getaddrinfo_fail)
def test_dns_resolution_failure_rejects():
    """Unresolvable hostnames must be rejected."""
    assert validate_webhook_url("https://nonexistent.invalid/webhook") is False
