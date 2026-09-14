"""Use case: derive lead time and cycle time from an issue's own history.

We deliberately don't use Jira's `resolutiondate` field: real data from this
workspace showed a Done issue with `resolutiondate: null` (its workflow
never wires a "resolution" transition), which would silently under-count
completed work. Instead we derive the actual completion time from the last
status-change into a Done-category status — which is always present for
anything that visibly reached Done.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from work_radar.application.status_catalog import merge_status_catalogs
from work_radar.domain.models import Issue, StatusCategory, StatusTransition
from work_radar.domain.ports import IssueHistoryRepository, IssueRepository, StatusCatalogRepository


@dataclass(frozen=True)
class CycleTimeResult:
    issue_key: str
    created_at: datetime
    done_at: datetime | None
    first_in_progress_at: datetime | None

    @property
    def lead_time_days(self) -> float | None:
        if self.done_at is None:
            return None
        return round((self.done_at - self.created_at).total_seconds() / 86400, 1)

    @property
    def cycle_time_days(self) -> float | None:
        if self.done_at is None or self.first_in_progress_at is None:
            return None
        return round((self.done_at - self.first_in_progress_at).total_seconds() / 86400, 1)


class CycleTimeCalculator:
    """Pure domain policy: no I/O, so it needs no mocking to unit test."""

    def __init__(self, status_catalog: dict[str, StatusCategory]) -> None:
        self._status_catalog = status_catalog

    def calculate(self, issue: Issue, transitions: list[StatusTransition]) -> CycleTimeResult:
        # Jira does not guarantee changelog order, so always sort explicitly.
        ordered = sorted(transitions, key=lambda t: t.occurred_at)

        done_at = None
        for transition in ordered:
            if self._category_of(transition.to_status) == StatusCategory.DONE:
                done_at = transition.occurred_at  # keep the *last* entry into Done

        first_in_progress_at = None
        for transition in ordered:
            if self._category_of(transition.to_status) == StatusCategory.IN_PROGRESS:
                first_in_progress_at = transition.occurred_at
                break  # keep the *first* entry into in-progress

        return CycleTimeResult(
            issue_key=issue.key,
            created_at=issue.created_at,
            done_at=done_at,
            first_in_progress_at=first_in_progress_at,
        )

    def _category_of(self, status_name: str) -> StatusCategory | None:
        return self._status_catalog.get(status_name)


@dataclass(frozen=True)
class CycleTimeReport:
    results: list[CycleTimeResult]

    @property
    def average_lead_time_days(self) -> float | None:
        return self._average(r.lead_time_days for r in self.results)

    @property
    def average_cycle_time_days(self) -> float | None:
        return self._average(r.cycle_time_days for r in self.results)

    @staticmethod
    def _average(values: Iterable[Optional[float]]) -> float | None:
        present = [v for v in values if v is not None]
        return round(sum(present) / len(present), 1) if present else None


DEFAULT_CYCLE_TIME_WINDOW_DAYS = 90


class CycleTimeReportService:
    """Fetches recently-done issues for a set of projects and times each one.

    Note: this makes one changelog request per issue on top of the initial
    search, so it's sized for tens-to-low-hundreds of issues, not a
    multi-year backfill.
    """

    def __init__(
        self,
        issue_repository: IssueRepository,
        history_repository: IssueHistoryRepository,
        status_catalog_repository: StatusCatalogRepository,
    ) -> None:
        self._issues = issue_repository
        self._history = history_repository
        self._status_catalogs = status_catalog_repository

    def build_report(
        self,
        project_keys: list[str],
        window_days: int = DEFAULT_CYCLE_TIME_WINDOW_DAYS,
    ) -> CycleTimeReport:
        done_issues = self._issues.find_done_issues_for_projects(project_keys, window_days=window_days)
        catalog = merge_status_catalogs(project_keys, self._status_catalogs)
        calculator = CycleTimeCalculator(catalog)

        results = [
            calculator.calculate(issue, self._history.get_transitions(issue.key)) for issue in done_issues
        ]
        return CycleTimeReport(results=results)
