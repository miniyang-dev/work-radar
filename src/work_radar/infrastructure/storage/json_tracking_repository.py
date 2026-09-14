"""JSON-file-backed TrackingItemRepository.

The only store in work-radar with no tracker behind it at all: these
records are typed in by hand and exist nowhere else, so this file *is*
the source of truth rather than a cache of someone else's data. That
also makes it the one feature that works with no Jira configuration.
"""
from __future__ import annotations

import json
import pathlib
from datetime import date, datetime

from work_radar.domain.models import (
    TrackingItem,
    TrackingNote,
    TrackingPriority,
    TrackingStatus,
)
from work_radar.infrastructure.storage.atomic_file import atomic_write_text


def _to_status(raw: object) -> TrackingStatus:
    """Unknown values fall back rather than raising.

    Mirrors the Jira mapper's "unknown category defaults to todo": one
    hand-edited (or older-schema) value in the file shouldn't make the
    whole list unreadable.
    """
    try:
        return TrackingStatus(raw)
    except ValueError:
        return TrackingStatus.TODO


def _to_priority(raw: object) -> TrackingPriority:
    try:
        return TrackingPriority(raw)
    except ValueError:
        return TrackingPriority.MEDIUM


def _to_notes(entry: dict) -> tuple[TrackingNote, ...]:
    """Reads the note log, upgrading records written before it existed.

    Older entries carry a single `note` string with no timestamp of its
    own; the best stamp available for it is the item's updated_at, which
    is when that text was last touched. Migrating on read (rather than
    rewriting the file up front) means the upgrade happens per record,
    the next time something saves it.
    """
    notes = entry.get("notes")
    if isinstance(notes, list):
        return tuple(
            TrackingNote(
                text=note["text"],
                created_at=datetime.fromisoformat(note["created_at"]),
            )
            for note in notes
        )

    legacy = entry.get("note")
    if not legacy:
        return ()
    return (TrackingNote(text=legacy, created_at=datetime.fromisoformat(entry["updated_at"])),)


class JsonTrackingRepository:
    def __init__(self, path: pathlib.Path) -> None:
        self._path = path

    def list_items(self) -> list[TrackingItem]:
        return self._read()

    def save(self, item: TrackingItem) -> None:
        """Upserts by id, replacing *in place* rather than moving the
        record to the end — editing an item shouldn't reshuffle the file
        under someone reading it, and display order is the service's job
        anyway.
        """
        items = self._read()
        for index, existing in enumerate(items):
            if existing.id == item.id:
                items[index] = item
                break
        else:
            items.append(item)
        self._write(items)

    def delete(self, item_id: str) -> None:
        self._write([item for item in self._read() if item.id != item_id])

    def _read(self) -> list[TrackingItem]:
        if not self._path.exists():
            return []
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        return [
            TrackingItem(
                id=entry["id"],
                item=entry["item"],
                # Only ever parses what this module's own isoformat() wrote
                # (offsets like "+08:00"), so Python 3.9's fromisoformat not
                # accepting a trailing "Z" can't bite here.
                created_at=datetime.fromisoformat(entry["created_at"]),
                updated_at=datetime.fromisoformat(entry["updated_at"]),
                status=_to_status(entry.get("status")),
                priority=_to_priority(entry.get("priority")),
                due_date=date.fromisoformat(entry["due_date"]) if entry.get("due_date") else None,
                owner=entry.get("owner"),
                # Absent in every record written before the field existed,
                # which .get reads as "not routed to anyone" — the same
                # thing the form's blank option means.
                member_account_id=entry.get("member_account_id"),
                link=entry.get("link"),
                notes=_to_notes(entry),
            )
            for entry in raw
        ]

    def _write(self, items: list[TrackingItem]) -> None:
        payload = [
            {
                "id": item.id,
                "item": item.item,
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
                "status": item.status.value,
                "priority": item.priority.value,
                "due_date": item.due_date.isoformat() if item.due_date else None,
                "owner": item.owner,
                "member_account_id": item.member_account_id,
                "link": item.link,
                "notes": [
                    {"text": note.text, "created_at": note.created_at.isoformat()}
                    for note in item.notes
                ],
            }
            for item in items
        ]
        atomic_write_text(self._path, json.dumps(payload, ensure_ascii=False, indent=2))
