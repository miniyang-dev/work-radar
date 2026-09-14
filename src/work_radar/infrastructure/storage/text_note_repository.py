"""A single persisted block of free-text — no structure, no domain model.

Used for the workload page's saved "intro" note (e.g. a standing strategy
blurb) that gets pasted above the generated weekly overview. Deliberately
skips a domain Protocol: there's no business rule here, just "remember
this string until someone overwrites it."
"""
from __future__ import annotations

import pathlib

from work_radar.infrastructure.storage.atomic_file import atomic_write_text


class TextNoteRepository:
    def __init__(self, path: pathlib.Path) -> None:
        self._path = path

    def read(self) -> str:
        if not self._path.exists():
            return ""
        return self._path.read_text(encoding="utf-8")

    def write(self, content: str) -> None:
        # An HTML form submits textarea content with CRLF line endings, but
        # reading the file back translates those to LF — so what was stored
        # never matched what was read, and the generated weekly overview
        # ended up splicing CRLF note text into LF-joined lines. Normalise
        # once, on the way in.
        atomic_write_text(self._path, content.replace("\r\n", "\n").replace("\r", "\n"))
