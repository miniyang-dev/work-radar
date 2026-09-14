"""Use case: summarize what changed for one person in the last N days.

Answers the question a PM would otherwise ask in a stand-up: what did you
finish, what did you touch but not finish, and what's just sitting there.
Built on the same status-transition history as cycle_time.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from work_radar.application.person_resolution import PersonResolver
from work_radar.application.stall_detection import StaleIssueFinder
from work_radar.application.status_catalog import merge_status_catalogs
from work_radar.domain.models import Issue, Person, StatusCategory
from work_radar.domain.ports import (
    IssueHistoryRepository,
    IssueRepository,
    PersonRepository,
    StatusCatalogRepository,
)

DEFAULT_WEEKLY_WINDOW_DAYS = 7


@dataclass(frozen=True)
class WeeklyReport:
    person: Person
    window_days: int
    completed: list[Issue] = field(default_factory=list)
    in_progress: list[Issue] = field(default_factory=list)
    stuck: list[Issue] = field(default_factory=list)


class WeeklyReportService:
    def __init__(
        self,
        issue_repository: IssueRepository,
        person_repository: PersonRepository,
        history_repository: IssueHistoryRepository,
        status_catalog_repository: StatusCatalogRepository,
        stale_finder: StaleIssueFinder | None = None,
    ) -> None:
        self._issues = issue_repository
        self._person_resolver = PersonResolver(person_repository)
        self._history = history_repository
        self._status_catalogs = status_catalog_repository
        self._stale_finder = stale_finder or StaleIssueFinder()

    def build_report(
        self,
        name_query: str,
        as_of: datetime,
        window_days: int = DEFAULT_WEEKLY_WINDOW_DAYS,
    ) -> WeeklyReport:
        person = self._person_resolver.resolve(name_query)
        return self.build_report_for_person(person, as_of, window_days)

    def build_report_for_person(
        self,
        person: Person,
        as_of: datetime,
        window_days: int = DEFAULT_WEEKLY_WINDOW_DAYS,
    ) -> WeeklyReport:
        """Skips name resolution entirely — for callers (e.g. a saved member
        roster) that already have a resolved Person on hand.
        """
        since = as_of - timedelta(days=window_days)

        touched = self._issues.find_issues_updated_since_for_assignee(person.account_id, window_days)
        touched_project_keys = sorted({issue.project_key for issue in touched})
        catalog = merge_status_catalogs(touched_project_keys, self._status_catalogs)

        # One batched request for every touched issue's history, rather
        # than one request per issue.
        transitions_by_key = self._history.get_transitions_for_issues([issue.key for issue in touched])

        completed: list[Issue] = []
        in_progress: list[Issue] = []
        for issue in touched:
            recent_transitions = [t for t in transitions_by_key.get(issue.key, []) if t.occurred_at >= since]
            if any(catalog.get(t.to_status) == StatusCategory.DONE for t in recent_transitions):
                completed.append(issue)
            elif recent_transitions or issue.is_open:
                # `or issue.is_open` catches work that was touched without
                # its status moving — a comment, a re-assignment, a due-date
                # change. Those issues used to fall out of the report
                # entirely, which contradicts "what did you touch but not
                # finish". An issue that is *already* done and merely got a
                # late comment still stays out: it wasn't completed in this
                # window, and it isn't in progress either.
                in_progress.append(issue)

        open_issues = self._issues.find_open_issues_for_assignee(person.account_id)
        stuck = self._stale_finder.find_stale(open_issues, as_of=as_of)

        return WeeklyReport(
            person=person,
            window_days=window_days,
            completed=completed,
            in_progress=in_progress,
            stuck=stuck,
        )
