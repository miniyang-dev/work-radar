"""Unit tests for JsonTrackingRepository, backed by a real file under tmp_path."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from work_radar.domain.models import (
    TrackingItem,
    TrackingNote,
    TrackingPriority,
    TrackingStatus,
)
from work_radar.infrastructure.storage.json_tracking_repository import JsonTrackingRepository

TAIPEI = timezone(timedelta(hours=8))
NOW = datetime(2026, 9, 8, 18, 30, tzinfo=TAIPEI)


def make_item(item_id="id-1", **overrides):
    fields = {
        "id": item_id,
        "item": f"item {item_id}",
        "created_at": NOW,
        "updated_at": NOW,
    }
    fields.update(overrides)
    return TrackingItem(**fields)


def test_list_items_is_empty_when_the_file_does_not_exist(tmp_path):
    assert JsonTrackingRepository(tmp_path / "tracking.json").list_items() == []


def test_save_round_trips_every_field_across_instances(tmp_path):
    path = tmp_path / "nested" / "tracking.json"
    item = make_item(
        item="跟法務確認 NDA",
        status=TrackingStatus.WAITING,
        priority=TrackingPriority.HIGH,
        due_date=date(2026, 9, 20),
        owner="Alice Wu",
        member_account_id="acc-1",
        link="https://example.com/doc",
        notes=(TrackingNote(text="週三前要回覆", created_at=NOW),),
    )

    JsonTrackingRepository(path).save(item)

    assert JsonTrackingRepository(path).list_items() == [item]


def test_save_keeps_an_optional_field_absent_as_none(tmp_path):
    path = tmp_path / "tracking.json"
    JsonTrackingRepository(path).save(make_item())

    restored = JsonTrackingRepository(path).list_items()[0]

    assert (restored.due_date, restored.owner, restored.link) == (None, None, None)
    assert restored.member_account_id is None
    assert restored.notes == ()


def test_save_upserts_by_id_in_place(tmp_path):
    path = tmp_path / "tracking.json"
    repository = JsonTrackingRepository(path)
    repository.save(make_item("id-1"))
    repository.save(make_item("id-2"))

    repository.save(make_item("id-1", item="改過的標題"))

    items = repository.list_items()
    # Editing must not reshuffle the file — id-1 stays first.
    assert [item.id for item in items] == ["id-1", "id-2"]
    assert items[0].item == "改過的標題"


def test_delete_removes_only_the_matching_id_and_ignores_an_unknown_one(tmp_path):
    path = tmp_path / "tracking.json"
    repository = JsonTrackingRepository(path)
    repository.save(make_item("id-1"))
    repository.save(make_item("id-2"))

    repository.delete("id-1")
    repository.delete("does-not-exist")

    assert [item.id for item in repository.list_items()] == ["id-2"]


def test_an_unrecognised_status_or_priority_falls_back_instead_of_raising(tmp_path):
    """A hand-edited (or older-schema) value shouldn't make the whole list
    unreadable — same choice the Jira status mapper makes.
    """
    path = tmp_path / "tracking.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "id-1",
                    "item": "x",
                    "created_at": NOW.isoformat(),
                    "updated_at": NOW.isoformat(),
                    "status": "wat",
                    "priority": "urgent-ish",
                }
            ]
        ),
        encoding="utf-8",
    )

    item = JsonTrackingRepository(path).list_items()[0]

    assert item.status == TrackingStatus.TODO
    assert item.priority == TrackingPriority.MEDIUM


def test_chinese_text_is_written_unescaped(tmp_path):
    path = tmp_path / "tracking.json"

    JsonTrackingRepository(path).save(make_item(item="追蹤合約進度"))

    assert "追蹤合約進度" in path.read_text(encoding="utf-8")


def test_a_note_log_round_trips_in_order_with_its_own_stamps(tmp_path):
    path = tmp_path / "tracking.json"
    earlier = TrackingNote(text="先問了 Carol", created_at=NOW)
    later = TrackingNote(text="還在等回覆", created_at=NOW + timedelta(days=1))
    JsonTrackingRepository(path).save(make_item(notes=(earlier, later)))

    assert JsonTrackingRepository(path).list_items()[0].notes == (earlier, later)


def test_a_record_written_before_the_note_log_becomes_one_entry(tmp_path):
    """The single `note` string had no stamp of its own, so updated_at —
    when that text was last touched — is the closest thing available.
    """
    path = tmp_path / "tracking.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "legacy",
                    "item": "客製媒體爬蟲",
                    "created_at": NOW.isoformat(),
                    "updated_at": (NOW + timedelta(hours=2)).isoformat(),
                    "note": "驗收中",
                }
            ]
        ),
        encoding="utf-8",
    )

    (restored,) = JsonTrackingRepository(path).list_items()

    assert restored.notes == (TrackingNote(text="驗收中", created_at=NOW + timedelta(hours=2)),)


def test_an_empty_legacy_note_leaves_the_log_empty(tmp_path):
    path = tmp_path / "tracking.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "legacy",
                    "item": "確認投票選項",
                    "created_at": NOW.isoformat(),
                    "updated_at": NOW.isoformat(),
                    "note": None,
                }
            ]
        ),
        encoding="utf-8",
    )

    assert JsonTrackingRepository(path).list_items()[0].notes == ()


def test_a_record_written_before_the_member_field_existed_still_reads(tmp_path):
    """The live file predates 個人工作量 routing, so every record in it is
    missing the key — which has to read as "not routed", not crash.
    """
    path = tmp_path / "tracking.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "id-1",
                    "item": "舊資料",
                    "created_at": NOW.isoformat(),
                    "updated_at": NOW.isoformat(),
                    "status": "todo",
                    "priority": "medium",
                    "due_date": None,
                    "owner": "Alice Wu",
                    "link": None,
                    "notes": [],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    (restored,) = JsonTrackingRepository(path).list_items()

    assert restored.member_account_id is None
    assert restored.owner == "Alice Wu"
