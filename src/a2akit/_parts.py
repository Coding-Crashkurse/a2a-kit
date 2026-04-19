"""Policy helpers for reading v10.Part lists.

Construction lives directly on ``v10.Part`` — as of ``a2a-pydantic>=0.0.8``
the library coerces raw dict/list into ``Value`` and raw bytes into base64,
so ``v10.Part(text=...)``, ``v10.Part(data={"k": "v"})``, and
``v10.Part(raw=b"...", filename="x")`` all just work.

What stays here is framework policy:

- ``FileInfo`` — a2akit's chosen shape for surfacing file attachments
  to user workers (decoded bytes vs URL, filename, media_type).
- ``extract_text`` / ``extract_files`` / ``extract_data`` — how a2akit
  joins / filters / unwraps across a list of parts. Different frameworks
  may choose different policies (space-join vs newline-join, dict-only
  data filter vs everything) so these are deliberately local.
- ``part_kind`` — tiny convenience for ``match`` statements at call sites.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from a2a_pydantic import v10


@dataclass(frozen=True)
class FileInfo:
    """User-facing description of a file part (either inline bytes or a URL)."""

    content: bytes | None
    url: str | None
    filename: str | None
    media_type: str | None


def part_kind(part: v10.Part) -> str:
    """Return one of 'text', 'raw', 'url', 'data', or 'empty'."""
    if part.text is not None:
        return "text"
    if part.raw is not None:
        return "raw"
    if part.url is not None:
        return "url"
    if part.data is not None:
        return "data"
    return "empty"


def extract_text(parts: list[v10.Part]) -> str:
    """Concatenate all text parts (newline-joined)."""
    texts = [p.text for p in parts if p.text is not None]
    return "\n".join(texts)


def extract_files(parts: list[v10.Part]) -> list[FileInfo]:
    """Return file-part metadata — inline bytes decoded, URLs preserved."""
    out: list[FileInfo] = []
    for p in parts:
        if p.raw is not None:
            out.append(
                FileInfo(
                    content=base64.b64decode(p.raw),
                    url=None,
                    filename=p.filename,
                    media_type=p.media_type,
                )
            )
        elif p.url is not None:
            out.append(
                FileInfo(
                    content=None,
                    url=p.url,
                    filename=p.filename,
                    media_type=p.media_type,
                )
            )
    return out


def extract_data(parts: list[v10.Part]) -> list[Any]:
    """Return the unwrapped content of each ``data`` part."""
    out: list[Any] = []
    for p in parts:
        if p.data is not None:
            out.append(p.data.root)
    return out


__all__ = [
    "FileInfo",
    "extract_data",
    "extract_files",
    "extract_text",
    "part_kind",
]
