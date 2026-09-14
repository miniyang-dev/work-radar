"""Tests for the terminal presenters."""
from __future__ import annotations

from datetime import datetime

from work_radar.application.cycle_time import CycleTimeReport, CycleTimeResult
from work_radar.cli.presenters import render_cycle_time_report


def _result(key: str, *, done_at: datetime | None, first_in_progress_at: datetime | None) -> CycleTimeResult:
    return CycleTimeResult(
        issue_key=key,
        created_at=datetime(2026, 1, 1, 10, 0),
        done_at=done_at,
        first_in_progress_at=first_in_progress_at,
    )


def test_a_same_day_turnaround_renders_as_zero_not_na():
    """`value or "N/A"` collapsed a real 0.0 measurement into "unknown":
    an issue created and finished within the hour rounds to 0.0 days.
    """
    same_day = _result(
        "GHI-1",
        done_at=datetime(2026, 1, 1, 10, 30),
        first_in_progress_at=datetime(2026, 1, 1, 10, 5),
    )

    output = render_cycle_time_report(CycleTimeReport(results=[same_day]), ["GHI"], 90)

    assert "lead=0.0d" in output
    assert "cycle=0.0d" in output
    assert "Average lead time: 0.0 day(s)" in output
    assert "N/A" not in output


def test_a_genuinely_unknown_measurement_still_renders_as_na():
    unfinished = _result("GHI-2", done_at=None, first_in_progress_at=None)

    output = render_cycle_time_report(CycleTimeReport(results=[unfinished]), ["GHI"], 90)

    assert "lead=N/Ad" in output
    assert "Average lead time: N/A day(s)" in output
