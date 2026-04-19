"""Protocol-version primitives used across a2akit."""

from __future__ import annotations

import os
from enum import StrEnum


class ProtocolVersion(StrEnum):
    """A2A protocol wire version supported by this server/client."""

    V0_3 = "0.3"
    V1_0 = "1.0"

    @classmethod
    def parse(cls, value: str | ProtocolVersion | None) -> ProtocolVersion:
        """Parse a protocol-version string tolerantly.

        Accepts "0.3", "0.3.0", "1.0", "1.0.0", ProtocolVersion instances,
        and None (which defaults to V1_0 unless the
        ``A2AKIT_DEFAULT_PROTOCOL_VERSION`` env var overrides it). Raises
        ValueError for anything else.
        """
        if value is None:
            env = os.environ.get("A2AKIT_DEFAULT_PROTOCOL_VERSION")
            if env is not None:
                return cls.parse(env)
            return cls.V1_0
        if isinstance(value, cls):
            return value
        s = str(value).strip()
        if s in ("0.3", "0.3.0"):
            return cls.V0_3
        if s in ("1.0", "1.0.0"):
            return cls.V1_0
        raise ValueError(f"Unsupported A2A protocol version: {value!r}")


SUPPORTED_VERSIONS: tuple[ProtocolVersion, ...] = (
    ProtocolVersion.V1_0,
    ProtocolVersion.V0_3,
)


ProtocolVersionInput = str | ProtocolVersion | None


def resolve_protocol_version(
    value: ProtocolVersionInput,
) -> ProtocolVersion:
    """Resolve the ``protocol_version`` kwarg to a single version.

    a2akit serves exactly one A2A wire version per :class:`A2AServer`. This
    is a deliberate design choice — dual-serving would require two wire
    stacks on one app, a shared JSON-RPC dispatcher that routes by method
    shape, and twin middleware pipelines. Clients with a mixed fleet should
    run two :class:`A2AServer` instances on different ports instead.

    ``None`` yields :meth:`ProtocolVersion.parse`'s default (``V1_0`` unless
    ``A2AKIT_DEFAULT_PROTOCOL_VERSION`` overrides it). Sets / frozensets are
    rejected with ``ValueError``.
    """
    if isinstance(value, (set, frozenset, list, tuple)):
        raise ValueError(
            "a2akit no longer supports dual protocol serving. Pass a single "
            f"version (e.g. protocol_version='1.0' or '0.3'), not {value!r}. "
            "If you need to serve v0.3 and v1.0 clients simultaneously, run "
            "two A2AServer instances on different ports."
        )
    return ProtocolVersion.parse(value)


__all__ = [
    "SUPPORTED_VERSIONS",
    "ProtocolVersion",
    "ProtocolVersionInput",
    "resolve_protocol_version",
]
