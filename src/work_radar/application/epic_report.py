"""Use case: build a status report for an Epic and its children.

Depends only on the IssueRepository Protocol (Dependency Inversion) — it
has no idea whether issues come from Jira, a fake in a test, or anything
else.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from work_radar.domain.models import Issue
from work_radar.domain.ports import IssueRepository


@dataclass(frozen=True)
class EpicReport:
    epic: Issue
    children: list[Issue] = field(default_factory=list)

    @property
    def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for child in self.children:
            counts[child.status.name] = counts.get(child.status.name, 0) + 1
        return counts

    @property
    def open_children(self) -> list[Issue]:
        return [child for child in self.children if child.is_open]


class EpicReportService:
    """Fetches an Epic and summarizes the state of its child issues."""

    def __init__(self, issue_repository: IssueRepository) -> None:
        self._issues = issue_repository

    def build_report(self, epic_key: str) -> EpicReport:
        epic = self._issues.get_issue(epic_key)
        children = self._issues.find_children(epic_key)
        return EpicReport(epic=epic, children=children)
