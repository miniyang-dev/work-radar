"""Unit tests for CycleTimeCalculator — pure logic, no I/O."""
from __future__ import annotations

from datetime import datetime, timezone

from work_radar.application.cycle_time import CycleTimeCalculator, CycleTimeReport
from work_radar.domain.models import StatusCategory, StatusTransition


def _dt(day: int) -> datetime:
    return datetime(2026, 8, day, tzinfo=timezone.utc)


def test_calculates_lead_and_cycle_time_from_transitions(make_issue):
    issue = make_issue("GHI-1", created_at=_dt(1))
    transitions = [
        StatusTransition(from_status="Submitted", to_status="Running", occurred_at=_dt(3)),
        StatusTransition(from_status="Running", to_status="Done", occurred_at=_dt(10)),
    ]
    catalog = {"Submitted": StatusCategory.TODO, "Running": StatusCategory.IN_PROGRESS, "Done": StatusCategory.DONE}

    result = CycleTimeCalculator(catalog).calculate(issue, transitions)

    assert result.lead_time_days == 9.0  # day 1 -> day 10
    assert result.cycle_time_days == 7.0  # day 3 -> day 10


def test_ignores_unordered_input(make_issue):
    """Jira doesn't guarantee changelog order; the calculator must sort itself."""
    issue = make_issue("GHI-1", created_at=_dt(1))
    transitions = [
        StatusTransition(from_status="Running", to_status="Done", occurred_at=_dt(10)),
        StatusTransition(from_status="Submitted", to_status="Running", occurred_at=_dt(3)),
    ]
    catalog = {"Submitted": StatusCategory.TODO, "Running": StatusCategory.IN_PROGRESS, "Done": StatusCategory.DONE}

    result = CycleTimeCalculator(catalog).calculate(issue, transitions)

    assert result.lead_time_days == 9.0
    assert result.cycle_time_days == 7.0


def test_not_yet_done_has_no_lead_or_cycle_time(make_issue):
    issue = make_issue("GHI-1", created_at=_dt(1))
    transitions = [StatusTransition(from_status="Submitted", to_status="Running", occurred_at=_dt(3))]
    catalog = {"Submitted": StatusCategory.TODO, "Running": StatusCategory.IN_PROGRESS}

    result = CycleTimeCalculator(catalog).calculate(issue, transitions)

    assert result.lead_time_days is None
    assert result.cycle_time_days is None


def test_done_without_ever_being_in_progress_has_lead_but_no_cycle_time(make_issue):
    issue = make_issue("GHI-1", created_at=_dt(1))
    transitions = [StatusTransition(from_status="Submitted", to_status="Done", occurred_at=_dt(5))]
    catalog = {"Submitted": StatusCategory.TODO, "Done": StatusCategory.DONE}

    result = CycleTimeCalculator(catalog).calculate(issue, transitions)

    assert result.lead_time_days == 4.0
    assert result.cycle_time_days is None


def test_keeps_the_last_transition_into_done_when_reopened(make_issue):
    """A ticket bouncing Done -> reopened -> Done again should use the
    final completion time, not the first."""
    issue = make_issue("GHI-1", created_at=_dt(1))
    transitions = [
        StatusTransition(from_status="Running", to_status="Done", occurred_at=_dt(5)),
        StatusTransition(from_status="Done", to_status="Running", occurred_at=_dt(6)),
        StatusTransition(from_status="Running", to_status="Done", occurred_at=_dt(12)),
    ]
    catalog = {"Running": StatusCategory.IN_PROGRESS, "Done": StatusCategory.DONE}

    result = CycleTimeCalculator(catalog).calculate(issue, transitions)

    assert result.lead_time_days == 11.0  # day 1 -> day 12, not day 5


def test_report_averages_ignore_issues_with_no_data():
    results = [
        _fake_result("GHI-1", lead=4.0, cycle=2.0),
        _fake_result("GHI-2", lead=None, cycle=None),
        _fake_result("GHI-3", lead=8.0, cycle=6.0),
    ]

    report = CycleTimeReport(results=results)

    assert report.average_lead_time_days == 6.0
    assert report.average_cycle_time_days == 4.0


def _fake_result(key, *, lead, cycle):
    from work_radar.application.cycle_time import CycleTimeResult

    created_at = _dt(1)
    done_at = created_at.replace(day=1 + int(lead)) if lead is not None else None
    first_in_progress_at = done_at.replace(day=done_at.day - int(cycle)) if (done_at and cycle is not None) else None
    return CycleTimeResult(
        issue_key=key,
        created_at=created_at,
        done_at=done_at,
        first_in_progress_at=first_in_progress_at,
    )
