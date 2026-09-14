"""Unit tests for TrackingListService.

Both impure dependencies are injected — a counting id factory and a `now`
passed per call — so nothing here monkeypatches uuid or the clock.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from work_radar.application.tracking_list import TrackingListService
from work_radar.domain.models import (
    TrackingItem,
    TrackingNote,
    TrackingPriority,
    TrackingStatus,
)

NOW = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)
LATER = NOW + timedelta(days=2)


class FakeTrackingItemRepository:
    def __init__(self, items=None):
        self.items = list(items or [])

    def list_items(self):
        return list(self.items)

    def save(self, item):
        for index, existing in enumerate(self.items):
            if existing.id == item.id:
                self.items[index] = item
                return
        self.items.append(item)

    def delete(self, item_id):
        self.items = [item for item in self.items if item.id != item_id]


def make_service(items=None):
    repository = FakeTrackingItemRepository(items)
    counter = {"n": 0}

    def next_id():
        counter["n"] += 1
        return f"id-{counter['n']}"

    return TrackingListService(repository, id_factory=next_id), repository


def make_item(item_id, **overrides):
    fields = {
        "id": item_id,
        "item": f"item {item_id}",
        "created_at": NOW,
        "updated_at": NOW,
    }
    fields.update(overrides)
    return TrackingItem(**fields)


def test_add_assigns_an_id_and_both_timestamps(tmp_path):
    service, repository = make_service()

    record = service.add(item="跟法務確認合約", now=NOW)

    assert record.id == "id-1"
    assert record.created_at == NOW
    assert record.updated_at == NOW
    assert record.status == TrackingStatus.TODO
    assert record.priority == TrackingPriority.MEDIUM
    assert repository.items == [record]


def test_add_strips_whitespace_and_rejects_a_blank_description():
    service, _ = make_service()

    assert service.add(item="  跟進報價  ", now=NOW).item == "跟進報價"
    with pytest.raises(ValueError):
        service.add(item="   ", now=NOW)


def test_update_preserves_the_id_and_created_at_while_advancing_updated_at():
    """The headline invariant: "how long has this sat untouched" is only
    meaningful if an edit can't quietly reset created_at.
    """
    service, _ = make_service([make_item("id-1", item="舊標題")])

    record = service.update(
        "id-1",
        now=LATER,
        item="新標題",
        status=TrackingStatus.WAITING,
        priority=TrackingPriority.HIGH,
        due_date=date(2026, 9, 20),
    )

    assert record.id == "id-1"
    assert record.created_at == NOW
    assert record.updated_at == LATER
    assert record.item == "新標題"
    assert record.status == TrackingStatus.WAITING
    assert record.priority == TrackingPriority.HIGH
    assert record.due_date == date(2026, 9, 20)


def test_add_stamps_the_first_note_with_the_same_now():
    service, _ = make_service()

    record = service.add(item="跟進報價", now=NOW, note="  先寄了信  ")

    assert record.notes == (TrackingNote(text="先寄了信", created_at=NOW),)


def test_add_without_a_note_starts_an_empty_log():
    service, _ = make_service()

    assert service.add(item="跟進報價", now=NOW, note=None).notes == ()
    assert service.add(item="跟進報價", now=NOW, note="   ").notes == ()


def test_update_appends_a_note_instead_of_replacing_the_log():
    """The whole point of the field: the earlier rounds of chasing stay
    readable, each with the time it was written.
    """
    first = TrackingNote(text="先問了 Carol", created_at=NOW)
    service, _ = make_service([make_item("id-1", notes=(first,))])

    record = service.update(
        "id-1",
        now=LATER,
        item="item id-1",
        status=TrackingStatus.WAITING,
        priority=TrackingPriority.MEDIUM,
        note="還在等回覆",
    )

    assert record.notes == (first, TrackingNote(text="還在等回覆", created_at=LATER))


def test_update_without_a_note_leaves_the_log_untouched():
    """Every edit posts the 備註 field, so a save that only moved the date
    must not leave a blank entry behind.
    """
    existing = TrackingNote(text="先問了 Carol", created_at=NOW)
    service, _ = make_service([make_item("id-1", notes=(existing,))])

    for blank in (None, "", "   \n  "):
        record = service.update(
            "id-1",
            now=LATER,
            item="item id-1",
            status=TrackingStatus.TODO,
            priority=TrackingPriority.MEDIUM,
            note=blank,
        )
        assert record.notes == (existing,)


def test_set_status_touches_only_the_status_and_the_clock():
    original = make_item("id-1", priority=TrackingPriority.HIGH, owner="Alice", due_date=date(2026, 9, 20))
    service, _ = make_service([original])

    record = service.set_status("id-1", TrackingStatus.DONE, now=LATER)

    assert record.status == TrackingStatus.DONE
    assert record.updated_at == LATER
    assert (record.item, record.priority, record.owner, record.due_date, record.created_at) == (
        original.item,
        original.priority,
        original.owner,
        original.due_date,
        original.created_at,
    )


def test_mutations_on_an_unknown_id_are_a_no_op():
    """A stale tab or a double-submitted form should change nothing, not
    raise — the route redirects either way.
    """
    original = make_item("id-1")
    service, repository = make_service([original])

    assert (
        service.update(
            "nope",
            now=LATER,
            item="x",
            status=TrackingStatus.DONE,
            priority=TrackingPriority.LOW,
        )
        is None
    )
    assert service.set_status("nope", TrackingStatus.DONE, now=LATER) is None
    service.delete("nope")

    assert repository.items == [original]


def test_delete_removes_only_the_matching_item():
    service, repository = make_service([make_item("id-1"), make_item("id-2")])

    service.delete("id-1")

    assert [item.id for item in repository.items] == ["id-2"]


def test_list_items_sorts_by_due_date_so_overdue_floats_to_the_top():
    undated = make_item("undated")
    soon = make_item("soon", due_date=date(2026, 9, 10))
    overdue = make_item("overdue", due_date=date(2026, 9, 1))
    service, _ = make_service([undated, soon, overdue])

    assert [item.id for item in service.list_items()] == ["overdue", "soon", "undated"]


def test_list_items_breaks_a_shared_due_date_by_priority_then_created_at():
    same_day = date(2026, 9, 10)
    low = make_item("low", due_date=same_day, priority=TrackingPriority.LOW)
    high = make_item("high", due_date=same_day, priority=TrackingPriority.HIGH)
    older_medium = make_item("older", due_date=same_day, created_at=NOW - timedelta(days=1))
    newer_medium = make_item("newer", due_date=same_day)
    service, _ = make_service([low, newer_medium, high, older_medium])

    assert [item.id for item in service.list_items()] == ["high", "older", "newer", "low"]
