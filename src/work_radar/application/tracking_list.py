"""Use case: work-radar's hand-kept list of things to follow up on.

Unlike every other service here, nothing in this one reaches for a
tracker — the items are typed in by a person and live only in the local
store. The service exists for four rules that would otherwise end up
scattered across a route handler and a template:

  - a new item gets an id and both timestamps, from injected sources so
    tests stay deterministic;
  - editing an item must preserve its `id` and `created_at` and only
    advance `updated_at` (rebuilding the dataclass in the route is
    exactly how that silently breaks, taking "how long has this sat
    untouched" with it);
  - a 備註 is appended, never replaced, and gets the same `now` as the
    edit that carried it — the field is a running log of what happened
    while chasing something, so overwriting it would throw away the only
    record of the earlier rounds;
  - ordering is a follow-up policy, not a rendering detail — soonest
    deadline first, so anything overdue floats to the top on its own.
"""
from __future__ import annotations

import dataclasses
from datetime import date, datetime
from typing import Callable
from uuid import uuid4

from work_radar.domain.models import (
    TrackingItem,
    TrackingNote,
    TrackingPriority,
    TrackingStatus,
)
from work_radar.domain.ports import TrackingItemRepository


def _new_id() -> str:
    return uuid4().hex


def _appended(
    notes: tuple[TrackingNote, ...], text: str | None, now: datetime
) -> tuple[TrackingNote, ...]:
    """Blank in, log unchanged — every edit posts the 備註 field, so most
    saves carry nothing new and must not leave an empty entry behind.
    """
    entry = (text or "").strip()
    if not entry:
        return notes
    return notes + (TrackingNote(text=entry, created_at=now),)


# Only used to break ties between items sharing a due date — the deadline
# itself always wins, since that's what actually makes something urgent.
_PRIORITY_ORDER = {
    TrackingPriority.HIGH: 0,
    TrackingPriority.MEDIUM: 1,
    TrackingPriority.LOW: 2,
}


class TrackingListService:
    def __init__(
        self,
        repository: TrackingItemRepository,
        id_factory: Callable[[], str] = _new_id,
    ) -> None:
        self._items = repository
        self._new_id = id_factory

    def list_items(self) -> list[TrackingItem]:
        """Soonest deadline first.

        Past dates already sort before today's, so overdue items reach the
        top without any special case; undated ones sort to `date.max` and
        settle at the bottom, which is the right default for a list whose
        whole point is "what needs chasing next".
        """
        return sorted(
            self._items.list_items(),
            key=lambda item: (
                item.due_date or date.max,
                _PRIORITY_ORDER.get(item.priority, len(_PRIORITY_ORDER)),
                item.created_at,
            ),
        )

    def add(
        self,
        *,
        item: str,
        now: datetime,
        status: TrackingStatus = TrackingStatus.TODO,
        priority: TrackingPriority = TrackingPriority.MEDIUM,
        due_date: date | None = None,
        owner: str | None = None,
        member_account_id: str | None = None,
        link: str | None = None,
        note: str | None = None,
    ) -> TrackingItem:
        summary = item.strip()
        if not summary:
            # The form marks the field required, so this only fires on a
            # hand-built POST — it's here to state the invariant, not to
            # handle a case the UI can produce.
            raise ValueError("A tracking item needs a non-empty description.")

        record = TrackingItem(
            id=self._new_id(),
            item=summary,
            created_at=now,
            updated_at=now,
            status=status,
            priority=priority,
            due_date=due_date,
            owner=owner,
            member_account_id=member_account_id,
            link=link,
            notes=_appended((), note, now),
        )
        self._items.save(record)
        return record

    def update(
        self,
        item_id: str,
        *,
        now: datetime,
        item: str,
        status: TrackingStatus,
        priority: TrackingPriority,
        due_date: date | None = None,
        owner: str | None = None,
        member_account_id: str | None = None,
        link: str | None = None,
        note: str | None = None,
    ) -> TrackingItem | None:
        """`note` is a *new* entry to append, not the field's new value:
        the form sends it empty unless someone typed something, and an
        empty one leaves the existing log untouched.

        Returns None when the id is unknown — a stale tab or a
        double-submitted form should be a no-op, not an error page.
        """
        existing = self._find(item_id)
        if existing is None:
            return None

        summary = item.strip()
        if not summary:
            raise ValueError("A tracking item needs a non-empty description.")

        # replace() on the stored record, so `id`, `created_at` and the
        # existing notes can't be dropped by an edit no matter what the
        # caller passes.
        record = dataclasses.replace(
            existing,
            item=summary,
            status=status,
            priority=priority,
            due_date=due_date,
            owner=owner,
            member_account_id=member_account_id,
            link=link,
            notes=_appended(existing.notes, note, now),
            updated_at=now,
        )
        self._items.save(record)
        return record

    def set_status(
        self, item_id: str, status: TrackingStatus, *, now: datetime
    ) -> TrackingItem | None:
        """The one-click "done" path — touches only the status and clock."""
        existing = self._find(item_id)
        if existing is None:
            return None
        record = dataclasses.replace(existing, status=status, updated_at=now)
        self._items.save(record)
        return record

    def delete(self, item_id: str) -> None:
        self._items.delete(item_id)

    def _find(self, item_id: str) -> TrackingItem | None:
        for item in self._items.list_items():
            if item.id == item_id:
                return item
        return None
