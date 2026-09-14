"""Use case: scan a batch of issues for common risk signals.

Each signal is a small, independently testable pure function; TeamRiskScanner
just composes them over the same issue list. Adding a fourth risk type means
adding one function + one field on TeamRiskReport — the existing ones never
change (Open/Closed).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from work_radar.application.stall_detection import StaleIssueFinder
from work_radar.domain.models import Issue
from work_radar.domain.ports import IssueRepository


def find_overdue(issues: list[Issue], as_of: date) -> list[Issue]:
    return [issue for issue in issues if issue.is_open and issue.due_date is not None and issue.due_date < as_of]


def find_unassigned(issues: list[Issue]) -> list[Issue]:
    return [issue for issue in issues if issue.is_open and issue.is_unassigned]


@dataclass(frozen=True)
class TeamRiskReport:
    overdue: list[Issue] = field(default_factory=list)
    unassigned: list[Issue] = field(default_factory=list)
    stale: list[Issue] = field(default_factory=list)


class TeamRiskScanner:
    def __init__(self, stale_finder: StaleIssueFinder | None = None) -> None:
        self._stale_finder = stale_finder or StaleIssueFinder()

    def scan(self, issues: list[Issue], as_of: datetime) -> TeamRiskReport:
        return TeamRiskReport(
            overdue=find_overdue(issues, as_of.date()),
            unassigned=find_unassigned(issues),
            stale=self._stale_finder.find_stale(issues, as_of),
        )


class TeamRiskReportService:
    """Fetches every open issue across a set of projects and scans it."""

    def __init__(self, issue_repository: IssueRepository, scanner: TeamRiskScanner | None = None) -> None:
        self._issues = issue_repository
        self._scanner = scanner or TeamRiskScanner()

    def build_report(self, project_keys: list[str], as_of: datetime) -> TeamRiskReport:
        issues = self._issues.find_open_issues_for_projects(project_keys)
        return self._scanner.scan(issues, as_of)
