"""Unit tests for the 追蹤事項 presenter.

Unlike the other presenter tests, these must hold with *no* Jira
configuration at all — that's the whole reason tracking_view is kept away
from _issue_url/_jira_domain.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from work_radar.domain.models import (
    TrackingItem,
    TrackingNote,
    TrackingPriority,
    TrackingStatus,
)
from work_radar.web.presenters import (
    tracking_priority_options,
    tracking_status_options,
    tracking_view,
    unticketed_by_member,
)

NOW = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)
TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)


def make_item(item_id="id-1", **overrides):
    fields = {"id": item_id, "item": f"item {item_id}", "created_at": NOW, "updated_at": NOW}
    fields.update(overrides)
    return TrackingItem(**fields)


def test_status_options_are_returned_in_display_order():
    assert [option["value"] for option in tracking_status_options()] == [
        "todo",
        "in_progress",
        "waiting",
        "done",
        "on_hold",
    ]
    assert [option["label"] for option in tracking_priority_options()] == ["高", "中", "低"]


def test_every_status_maps_to_a_label_and_a_css_class():
    items = [make_item(status.value, status=status) for status in TrackingStatus]

    view = tracking_view(items)
    rows = {row["id"]: row for row in view["active"] + view["closed"]}

    assert rows["waiting"]["status_label"] == "等待回覆"
    assert rows["waiting"]["status_css"] == "status-waiting"
    assert rows["on_hold"]["status_css"] == "status-hold"
    assert rows["done"]["status_css"] == "status-done"
    assert rows["todo"]["status_css"] == "status-todo"
    assert rows["in_progress"]["status_css"] == "status-progress"


def test_only_an_active_item_with_a_past_date_counts_as_overdue():
    """A closed item with a date in the past isn't something to chase."""
    active = make_item("active", due_date=YESTERDAY)
    finished = make_item("finished", due_date=YESTERDAY, status=TrackingStatus.DONE)
    upcoming = make_item("upcoming", due_date=TOMORROW)

    view = tracking_view([active, finished, upcoming])
    by_id = {row["id"]: row for row in view["active"] + view["closed"]}

    assert by_id["active"]["is_overdue"] is True
    assert by_id["finished"]["is_overdue"] is False
    assert by_id["upcoming"]["is_overdue"] is False
    assert view["counts"]["overdue"] == 1


def test_the_view_splits_active_from_closed_and_counts_both():
    items = [
        make_item("a", status=TrackingStatus.TODO),
        make_item("b", status=TrackingStatus.WAITING),
        make_item("c", status=TrackingStatus.DONE),
        make_item("d", status=TrackingStatus.ON_HOLD),
    ]

    view = tracking_view(items)

    assert [row["id"] for row in view["active"]] == ["a", "b"]
    assert sorted(row["id"] for row in view["closed"]) == ["c", "d"]
    assert view["counts"] == {"active": 2, "overdue": 0, "waiting": 1, "closed": 2}


def test_closed_items_are_ordered_most_recently_touched_first():
    older = make_item("older", status=TrackingStatus.DONE, updated_at=NOW)
    newer = make_item("newer", status=TrackingStatus.DONE, updated_at=NOW + timedelta(days=1))

    view = tracking_view([older, newer])

    assert [row["id"] for row in view["closed"]] == ["newer", "older"]


def test_a_non_http_link_never_reaches_an_href():
    items = [
        make_item("evil", link="javascript:alert(1)"),
        make_item("relative", link="/etc/passwd"),
        make_item("fine", link="https://example.com"),
    ]

    rows = {row["id"]: row for row in tracking_view(items)["active"]}

    assert rows["evil"]["link"] is None
    assert rows["relative"]["link"] is None
    assert rows["fine"]["link"] == "https://example.com"


def test_due_date_is_an_iso_string_so_it_can_prefill_a_date_input():
    rows = {
        row["id"]: row
        for row in tracking_view([make_item("dated", due_date=date(2026, 9, 20)), make_item("undated")])["active"]
    }

    assert rows["dated"]["due_date"] == "2026-09-20"
    assert rows["undated"]["due_date"] == ""


def test_an_owner_gets_an_avatar_and_a_blank_one_does_not():
    rows = {row["id"]: row for row in tracking_view([make_item("named", owner="Alice Wu"), make_item("blank")])["active"]}

    assert rows["named"]["owner_avatar"]["initials"] == "AW"
    assert rows["blank"]["owner_avatar"] is None
    assert rows["blank"]["owner"] == ""


def test_every_note_carries_its_own_stamp_in_the_order_it_was_written():
    """The cell reads as a log, so the order is the order they were typed
    and each line keeps the time it was added — not the item's updated_at.
    """
    item = make_item(
        notes=(
            TrackingNote(text="先問了 Carol", created_at=NOW),
            TrackingNote(text="還在等回覆", created_at=NOW + timedelta(days=1)),
        )
    )

    (row,) = tracking_view([item])["active"]

    assert [(note["text"], note["created_at"]) for note in row["notes"]] == [
        ("先問了 Carol", "2026-09-08 10:00"),
        ("還在等回覆", "2026-09-09 10:00"),
    ]


def test_an_item_with_no_notes_renders_an_empty_log():
    (row,) = tracking_view([make_item()])["active"]

    assert row["notes"] == []


def test_every_row_says_whether_it_is_still_being_chased():
    """Drives the one-click action: 完成 on an open row, 重新追蹤 on a
    closed one, from the same macro.
    """
    view = tracking_view(
        [
            make_item("open"),
            make_item("finished", status=TrackingStatus.DONE),
            make_item("parked", status=TrackingStatus.ON_HOLD),
        ]
    )

    assert [row["is_active"] for row in view["active"]] == [True]
    assert [row["is_active"] for row in view["closed"]] == [False, False]


def test_a_note_url_is_rendered_as_a_short_label_keeping_the_real_href():
    """A pasted Google Sheets URL has no spaces in it, so printing it in
    full cannot wrap and dragged the whole table into a scrollbar.
    """
    url = (
        "https://docs.google.com/spreadsheets/d/"
        "1MlGmnyuDGHJVj5V0tgonI49-rFj1-QX-pK3tJPH240Q/edit?gid=0#gid=0"
    )
    item = make_item(notes=(TrackingNote(text=f"補量追蹤表 {url}", created_at=NOW),))

    (row,) = tracking_view([item])["active"]
    (note,) = row["notes"]

    assert note["segments"] == [
        {"text": "補量追蹤表 "},
        {"text": "docs.google.com/spreadsheets/d/…", "url": url},
    ]
    # The raw text is still there for anything that wants it verbatim.
    assert note["text"] == f"補量追蹤表 {url}"


def test_a_note_link_stops_at_the_chinese_sentence_it_sits_in():
    """"not whitespace" is too greedy for these notes: 「…/GHI-1676。後續再談」
    ended up as one link with the prose inside its href.
    """
    item = make_item(
        notes=(
            TrackingNote(
                text="驗收中 https://example.atlassian.net/browse/GHI-1676。待上游資料落地",
                created_at=NOW,
            ),
        )
    )

    (row,) = tracking_view([item])["active"]
    (note,) = row["notes"]

    assert note["segments"] == [
        {"text": "驗收中 "},
        {
            "text": "example.atlassian.net/browse/GHI-1676",
            "url": "https://example.atlassian.net/browse/GHI-1676",
        },
        {"text": "。待上游資料落地"},
    ]


def test_a_note_link_drops_the_punctuation_that_followed_it():
    item = make_item(
        notes=(TrackingNote(text="見 (https://example.com/a/b), 謝謝", created_at=NOW),),
    )

    (row,) = tracking_view([item])["active"]
    (note,) = row["notes"]

    assert note["segments"] == [
        {"text": "見 ("},
        {"text": "example.com/a/b", "url": "https://example.com/a/b"},
        {"text": "), 謝謝"},
    ]


def test_a_short_note_url_is_left_readable_in_full():
    item = make_item(notes=(TrackingNote(text="https://example.com/about", created_at=NOW),))

    (row,) = tracking_view([item])["active"]
    (note,) = row["notes"]

    assert note["segments"] == [{"text": "example.com/about", "url": "https://example.com/about"}]


def test_a_note_without_a_link_is_one_plain_segment():
    item = make_item(notes=(TrackingNote(text="單子已補開", created_at=NOW),))

    (row,) = tracking_view([item])["active"]
    (note,) = row["notes"]

    assert note["segments"] == [{"text": "單子已補開"}]


def test_a_routed_item_carries_the_member_id_and_a_readable_name():
    item = make_item(member_account_id="acc-1")

    (row,) = tracking_view([item], member_names={"acc-1": "Alice Wu"})["active"]

    assert row["member_account_id"] == "acc-1"
    assert row["member_name"] == "Alice Wu"


def test_an_unrouted_item_has_no_member_at_all():
    (row,) = tracking_view([make_item()], member_names={"acc-1": "Alice Wu"})["active"]

    assert row["member_account_id"] == ""
    assert row["member_name"] == ""


def test_a_member_who_left_the_roster_keeps_the_id_but_loses_the_name():
    """The roster can shrink under a tracking item; the row still has to
    render rather than blow up on the missing name.
    """
    (row,) = tracking_view([make_item(member_account_id="acc-gone")], member_names={})["active"]

    assert row["member_account_id"] == "acc-gone"
    assert row["member_name"] == ""


def test_unticketed_by_member_groups_only_what_is_still_being_chased():
    routed = make_item("a", member_account_id="acc-1")
    also_routed = make_item("b", member_account_id="acc-1")
    someone_else = make_item("c", member_account_id="acc-2")
    unrouted = make_item("d")
    closed = make_item("e", member_account_id="acc-1", status=TrackingStatus.DONE)
    parked = make_item("f", member_account_id="acc-1", status=TrackingStatus.ON_HOLD)

    grouped = unticketed_by_member([routed, also_routed, someone_else, unrouted, closed, parked])

    assert [item.id for item in grouped["acc-1"]] == ["a", "b"]
    assert [item.id for item in grouped["acc-2"]] == ["c"]
    assert "" not in grouped
