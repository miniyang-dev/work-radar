"""JSON-file-backed store of one status line per ticket key.

Backs the weekly overview's hand-written follow-up text ("待PM驗完品質…"):
the ticket list itself is re-read from Jira every time, and only what a
person typed under a ticket is remembered here, keyed by ticket key — so it
reappears the next week if that ticket is still in flight, and is simply
never looked at if it isn't. Like TextNoteRepository there is no domain
Protocol: no business rule, just "remember this text for that key".
"""
from __future__ import annotations

import json
import pathlib

from work_radar.infrastructure.storage.atomic_file import atomic_write_text


class JsonIssueNoteRepository:
    def __init__(self, path: pathlib.Path) -> None:
        self._path = path

    def read_all(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def update(self, notes: dict[str, str]) -> None:
        """Merges `notes` into what is stored. A blank note deletes the
        entry, so clearing a line in the overview forgets it rather than
        keeping an empty string around. Keys not mentioned are untouched:
        a ticket that dropped out of this week's list keeps its text.
        """
        stored = self.read_all()
        for key, note in notes.items():
            if note.strip():
                stored[key] = note
            else:
                stored.pop(key, None)
        atomic_write_text(self._path, json.dumps(stored, ensure_ascii=False, indent=2, sort_keys=True))
