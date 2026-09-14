"""Unit tests for StaleIssueFinder — pure domain logic, no I/O involved."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from work_radar.application.stall_detection import StaleIssueFinder
from work_radar.domain.models import StatusCategory

AS_OF = datetime(2026, 9, 7, tzinfo=timezone.utc)


def test_finds_open_issues_older_than_threshold(make_issue):
    stale = make_issue(
        "GHI-1",
        status_category=StatusCategory.IN_PROGRESS,
        updated_at=AS_OF - timedelta(days=40),
    )
    fresh = make_issue(
        "GHI-2",
        status_category=StatusCategory.IN_PROGRESS,
        updated_at=AS_OF - timedelta(days=1),
    )
    finder = StaleIssueFinder(threshold_days=14)

    result = finder.find_stale([stale, fresh], as_of=AS_OF)

    assert result == [stale]


def test_ignores_done_issues_regardless_of_age(make_issue):
    old_but_done = make_issue(
        "GHI-3",
        status_category=StatusCategory.DONE,
        updated_at=AS_OF - timedelta(days=400),
    )
    finder = StaleIssueFinder(threshold_days=14)

    result = finder.find_stale([old_but_done], as_of=AS_OF)

    assert result == []


def test_issue_exactly_at_threshold_is_not_yet_stale(make_issue):
    boundary = make_issue(
        "GHI-4",
        status_category=StatusCategory.IN_PROGRESS,
        updated_at=AS_OF - timedelta(days=14),
    )
    finder = StaleIssueFinder(threshold_days=14)

    result = finder.find_stale([boundary], as_of=AS_OF)

    assert result == []
