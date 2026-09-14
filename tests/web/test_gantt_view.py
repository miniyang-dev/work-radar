"""Unit tests for gantt_view — the three-week Gantt chart (last week plus
the next two).

Uses the real presenters module, which builds issue URLs from the Jira
settings conftest pins for the whole suite — no .env and no network.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from work_radar.application.workload_report import WorkloadReport
from work_radar.domain.models import Person, StatusCategory
from work_radar.web.presenters import gantt_view

TODAY = date.today()
NOW = datetime.now(timezone.utc)
WINDOW_START = TODAY - timedelta(days=7)
WINDOW_END = TODAY + timedelta(days=14)
# Today sits 7 days into a 21-day axis.
TODAY_PCT = 33.33


def test_gantt_view_draws_completed_work_from_start_to_completion(make_issue):
    """The bar ends on what happened, not on what was promised: this one
    was due Friday but landed on Wednesday.
    """
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    finished = make_issue(
        "ABC-1583",
        status_name="Done",
        status_category=StatusCategory.DONE,
        start_date=WINDOW_START + timedelta(days=3),
        due_date=WINDOW_START + timedelta(days=5),
        completed_at=datetime.combine(
            WINDOW_START + timedelta(days=4), time(17, 3), tzinfo=timezone.utc
        ),
    )
    report = WorkloadReport(person=alice, done_issues=[finished])

    [group] = gantt_view([report])["groups"]
    [row] = group["rows"]

    assert row["status"] == "completed"
    # Days 3 and 4 of the axis — two inclusive days, ending a day earlier
    # than the due date would have drawn it.
    assert row["left_pct"] == 14.29
    assert row["width_pct"] == 9.52


def test_gantt_view_lists_completed_work_above_active_work(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    active = make_issue("GHI-1", status_name="Running", due_date=TODAY + timedelta(days=2))
    finished = make_issue(
        "GHI-2",
        status_name="Done",
        status_category=StatusCategory.DONE,
        completed_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    report = WorkloadReport(person=alice, issues=[active], done_issues=[finished])

    [group] = gantt_view([report])["groups"]

    assert [row["key"] for row in group["rows"]] == ["GHI-2", "GHI-1"]


def test_gantt_view_includes_a_member_whose_only_work_is_finished(make_issue):
    """Someone can close out everything they had open — the Gantt still has
    to show what they did, same as their table does.
    """
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    finished = make_issue(
        "GHI-2",
        status_name="Done",
        status_category=StatusCategory.DONE,
        completed_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    report = WorkloadReport(person=alice, issues=[], done_issues=[finished])

    [group] = gantt_view([report])["groups"]

    assert group["member"] == "Alice Wu"
    assert [row["key"] for row in group["rows"]] == ["GHI-2"]


def test_gantt_view_completed_bar_without_a_timestamp_falls_back_to_due_date(make_issue):
    """Jira only sets a completion time if the status history has one; a
    ticket closed without it still needs a bar.
    """
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    finished = make_issue(
        "GHI-2",
        status_name="Done",
        status_category=StatusCategory.DONE,
        start_date=WINDOW_START + timedelta(days=1),
        due_date=WINDOW_START + timedelta(days=2),
        completed_at=None,
    )
    report = WorkloadReport(person=alice, done_issues=[finished])

    [group] = gantt_view([report])["groups"]
    [row] = group["rows"]

    assert row["status"] == "completed"
    assert row["left_pct"] == 4.76
    assert row["width_pct"] == 9.52


def test_gantt_view_completed_bar_survives_a_start_date_after_completion(make_issue):
    """Bulk-closed housekeeping tickets turn up with exactly this shape."""
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    finished = make_issue(
        "GHI-2",
        status_name="Done",
        status_category=StatusCategory.DONE,
        start_date=TODAY + timedelta(days=5),
        completed_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    report = WorkloadReport(person=alice, done_issues=[finished])

    [group] = gantt_view([report])["groups"]
    [row] = group["rows"]

    # One day wide at the start date, rather than a backwards bar or a
    # collapsed marker.
    assert row["width_pct"] == 4.76


def test_gantt_view_is_empty_when_no_active_issues(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    report = WorkloadReport(person=alice, issues=[make_issue("GHI-1", status_name="Pending")])

    assert gantt_view([report]) == {
        "groups": [],
        "window_start": WINDOW_START.isoformat(),
        "window_end": WINDOW_END.isoformat(),
        "today": TODAY.isoformat(),
        "today_pct": TODAY_PCT,
    }


def test_gantt_view_skips_members_with_no_active_issues(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    amy = Person(account_id="acc-2", display_name="Amy Lin")
    reports = [
        WorkloadReport(person=alice, issues=[make_issue("GHI-1", status_name="Pending")]),
        WorkloadReport(person=amy, issues=[make_issue("GHI-2", status_name="Running")]),
    ]

    gantt = gantt_view(reports)

    assert [group["member"] for group in gantt["groups"]] == ["Amy Lin"]


def test_gantt_view_classifies_overdue_due_soon_beyond_window_and_open_ended(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    overdue = make_issue("GHI-1", status_name="Running", due_date=TODAY - timedelta(days=2))
    due_soon = make_issue("GHI-2", status_name="Reviewing", due_date=TODAY + timedelta(days=5))
    beyond_window = make_issue("GHI-3", status_name="Running", due_date=TODAY + timedelta(days=30))
    open_ended = make_issue("GHI-4", status_name="Reviewing", due_date=None)
    report = WorkloadReport(person=alice, issues=[overdue, due_soon, beyond_window, open_ended])

    [group] = gantt_view([report])["groups"]
    rows_by_key = {row["key"]: row for row in group["rows"]}

    assert rows_by_key["GHI-1"]["status"] == "overdue"
    assert rows_by_key["GHI-2"]["status"] == "due_soon"
    assert rows_by_key["GHI-3"]["status"] == "beyond_window"
    assert rows_by_key["GHI-4"]["status"] == "open_ended"
    assert rows_by_key["GHI-3"]["width_pct"] == 100.0
    assert rows_by_key["GHI-4"]["width_pct"] == 100.0
    assert 0 < rows_by_key["GHI-2"]["width_pct"] < 100.0
    # No start date set, so all four fall back to a creation date that
    # predates the window and clip to its left edge.
    assert {row["left_pct"] for row in group["rows"]} == {0.0}


def test_gantt_view_bar_spans_start_date_to_due_date(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    issue = make_issue(
        "GHI-1",
        status_name="Running",
        start_date=TODAY + timedelta(days=7),
        due_date=TODAY + timedelta(days=14),
    )
    report = WorkloadReport(person=alice, issues=[issue])

    [group] = gantt_view([report])["groups"]
    [row] = group["rows"]

    assert row["left_pct"] == 66.67
    assert row["width_pct"] == 33.33


def test_gantt_view_same_day_start_and_due_is_one_day_wide(make_issue):
    """The bug this replaced: a one-day task due late in the window drew a
    bar from today all the way to its due date.
    """
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    same_day = TODAY + timedelta(days=12)
    issue = make_issue("GHI-1", status_name="Running", start_date=same_day, due_date=same_day)
    report = WorkloadReport(person=alice, issues=[issue])

    [group] = gantt_view([report])["groups"]
    [row] = group["rows"]

    assert row["left_pct"] == 90.48
    # One day of a 21-day axis — not a fixed marker, and not the whole row.
    assert row["width_pct"] == 4.76


def test_gantt_view_clips_a_start_date_already_in_the_past(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    issue = make_issue(
        "GHI-1",
        status_name="Running",
        start_date=TODAY - timedelta(days=30),
        due_date=TODAY + timedelta(days=7),
    )
    report = WorkloadReport(person=alice, issues=[issue])

    [group] = gantt_view([report])["groups"]
    [row] = group["rows"]

    assert row["left_pct"] == 0.0
    assert row["width_pct"] == 71.43


def test_gantt_view_bar_at_the_window_end_stays_inside_the_track(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    at_window_end = TODAY + timedelta(days=14)
    issue = make_issue("GHI-1", status_name="Running", start_date=at_window_end, due_date=at_window_end)
    report = WorkloadReport(person=alice, issues=[issue])

    [group] = gantt_view([report])["groups"]
    [row] = group["rows"]

    assert row["left_pct"] + row["width_pct"] == 100.0
    assert row["width_pct"] == 3.0


def test_gantt_view_open_ended_bar_starts_at_its_start_date(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    issue = make_issue("GHI-1", status_name="Running", start_date=TODAY + timedelta(days=7), due_date=None)
    report = WorkloadReport(person=alice, issues=[issue])

    [group] = gantt_view([report])["groups"]
    [row] = group["rows"]

    assert row["status"] == "open_ended"
    assert row["left_pct"] == 66.67
    assert row["width_pct"] == 33.33


def test_gantt_view_overdue_span_is_drawn_at_full_length_before_today(make_issue):
    """The bug this replaced: an overdue span collapsed into a fixed marker
    at the left edge, so a three-day task that ended last Wednesday was
    indistinguishable from one that ran for a month.
    """
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    issue = make_issue(
        "GHI-1",
        status_name="Running",
        start_date=TODAY - timedelta(days=4),
        due_date=TODAY - timedelta(days=2),
    )
    report = WorkloadReport(person=alice, issues=[issue])

    [group] = gantt_view([report])["groups"]
    [row] = group["rows"]

    assert row["status"] == "overdue"
    # Three inclusive days (09/07~09/09 style), so three 21ths of the axis.
    assert row["left_pct"] == 14.29
    assert row["width_pct"] == 14.29
    assert row["left_pct"] + row["width_pct"] < TODAY_PCT


def test_gantt_view_a_due_date_before_its_start_date_still_renders(make_issue):
    """Jira lets the two dates be entered the wrong way round; the bar has
    to stay a visible marker rather than take a negative width.
    """
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    issue = make_issue(
        "GHI-1",
        status_name="Running",
        start_date=TODAY + timedelta(days=3),
        due_date=TODAY - timedelta(days=1),
    )
    report = WorkloadReport(person=alice, issues=[issue])

    [group] = gantt_view([report])["groups"]
    [row] = group["rows"]

    assert row["width_pct"] == 3.0


def test_gantt_view_sorts_overdue_first_then_by_due_date(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    later = make_issue("GHI-1", status_name="Running", due_date=TODAY + timedelta(days=10))
    overdue = make_issue("GHI-2", status_name="Running", due_date=TODAY - timedelta(days=1))
    sooner = make_issue("GHI-3", status_name="Running", due_date=TODAY + timedelta(days=2))
    no_due_date = make_issue("GHI-4", status_name="Running", due_date=None)
    report = WorkloadReport(person=alice, issues=[later, overdue, sooner, no_due_date])

    [group] = gantt_view([report])["groups"]

    assert [row["key"] for row in group["rows"]] == ["GHI-2", "GHI-3", "GHI-1", "GHI-4"]


def test_gantt_view_window_spans_last_week_and_the_next_two(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    report = WorkloadReport(person=alice, issues=[make_issue("GHI-1", status_name="Running")])

    gantt = gantt_view([report])

    assert gantt["window_start"] == WINDOW_START.isoformat()
    assert gantt["window_end"] == WINDOW_END.isoformat()
    assert gantt["today"] == TODAY.isoformat()
    assert gantt["today_pct"] == TODAY_PCT


def test_gantt_view_window_start_always_reaches_this_weeks_monday(make_issue):
    """The weekly review looks back to Monday, so the left edge has to sit
    on or before it on every weekday — including Sunday, where Monday is
    only six days back.
    """
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    report = WorkloadReport(person=alice, issues=[make_issue("GHI-1", status_name="Running")])

    window_start = date.fromisoformat(gantt_view([report])["window_start"])
    this_monday = TODAY - timedelta(days=TODAY.weekday())

    assert window_start <= this_monday
