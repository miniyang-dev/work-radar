"""Unit tests for the team risk finders — pure logic, no I/O."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from work_radar.application.risk_scan import TeamRiskScanner, find_overdue, find_unassigned
from work_radar.domain.models import Person, StatusCategory

AS_OF = datetime(2026, 9, 7, tzinfo=timezone.utc)


def test_find_overdue_excludes_done_and_future_due_dates(make_issue):
    overdue = make_issue("GHI-1", status_category=StatusCategory.IN_PROGRESS, due_date=date(2026, 9, 1))
    not_yet_due = make_issue("GHI-2", status_category=StatusCategory.IN_PROGRESS, due_date=date(2026, 9, 30))
    done_but_overdue = make_issue(
        "GHI-3", status_category=StatusCategory.DONE, due_date=date(2026, 8, 1)
    )
    no_due_date = make_issue("GHI-4", status_category=StatusCategory.IN_PROGRESS)

    result = find_overdue([overdue, not_yet_due, done_but_overdue, no_due_date], as_of=AS_OF.date())

    assert result == [overdue]


def test_find_unassigned_excludes_done_and_assigned(make_issue):
    someone = Person(account_id="acc-1", display_name="Alice Wu")
    unassigned_open = make_issue("GHI-1", status_category=StatusCategory.TODO, assignee=None)
    assigned_open = make_issue("GHI-2", status_category=StatusCategory.TODO, assignee=someone)
    unassigned_done = make_issue("GHI-3", status_category=StatusCategory.DONE, assignee=None)

    result = find_unassigned([unassigned_open, assigned_open, unassigned_done])

    assert result == [unassigned_open]


def test_scanner_combines_all_three_signals(make_issue):
    someone = Person(account_id="acc-1", display_name="Alice Wu")
    overdue = make_issue(
        "GHI-1",
        status_category=StatusCategory.IN_PROGRESS,
        due_date=date(2026, 9, 1),
        assignee=someone,
        updated_at=AS_OF,
    )
    unassigned = make_issue("GHI-2", status_category=StatusCategory.TODO, assignee=None, updated_at=AS_OF)
    stale = make_issue(
        "GHI-3",
        status_category=StatusCategory.IN_PROGRESS,
        updated_at=AS_OF - timedelta(days=40),
        assignee=someone,
    )
    healthy = make_issue(
        "GHI-4", status_category=StatusCategory.IN_PROGRESS, updated_at=AS_OF, assignee=someone
    )

    report = TeamRiskScanner().scan([overdue, unassigned, stale, healthy], as_of=AS_OF)

    assert report.overdue == [overdue]
    assert report.unassigned == [unassigned]
    assert report.stale == [stale]
