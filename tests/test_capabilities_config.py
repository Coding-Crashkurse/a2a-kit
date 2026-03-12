"""Unit tests for CapabilitiesConfig validation."""

from __future__ import annotations

import pytest
from a2a.types import AgentExtension

from a2akit.agent_card import CapabilitiesConfig


def test_default_capabilities():
    """All capabilities default to False, no error."""
    caps = CapabilitiesConfig()
    assert caps.streaming is False
    assert caps.push_notifications is False
    assert caps.extended_agent_card is False
    assert caps.extensions is None


def test_streaming_enabled():
    """streaming=True works without error."""
    caps = CapabilitiesConfig(streaming=True)
    assert caps.streaming is True


def test_push_notifications_raises():
    """push_notifications=True raises NotImplementedError."""
    with pytest.raises(NotImplementedError, match="push_notifications"):
        CapabilitiesConfig(push_notifications=True)


def test_extended_agent_card_raises():
    """extended_agent_card=True raises NotImplementedError."""
    with pytest.raises(NotImplementedError, match="extended_agent_card"):
        CapabilitiesConfig(extended_agent_card=True)


def test_extensions_raises():
    """extensions=[...] raises NotImplementedError."""
    ext = AgentExtension(uri="urn:example:ext")
    with pytest.raises(NotImplementedError, match="extensions"):
        CapabilitiesConfig(extensions=[ext])
