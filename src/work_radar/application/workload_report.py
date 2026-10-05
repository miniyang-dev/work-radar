"""Use case: resolve a person by name and list their currently open issues."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import cached_property

from work_radar.application.person_resolution import PersonResolver
from work_radar.domain.models import Issue, Person
from work_radar.domain.ports import IssueRepository, PersonRepository

# Status *names* (matched as a case-insensitive substring, since Jira's
# actual names are bilingual e.g. "Running / 執行中") that count as active
# work — actually being executed or reviewed right now, as opposed to
# queued/pending/approved-but-not-started work sitting in the backlog.
_ACTIVE_STATUS_KEYWORDS = ("running", "reviewing")
_REVIEWING_STATUS_KEYWORD = "reviewing"


def is_reviewing(issue: Issue) -> bool:
    """Work that is finished on the assignee's side and waiting on someone
    else's verdict — still active, but no longer what they're driving.
    """
    return _REVIEWING_STATUS_KEYWORD in issue.status.name.lower()


def start_of_week(today: date) -> date:
    """Monday of the week `today` falls in — the boundary the team's weekly
    review already uses, so "this week" means the same thing here as it
    does in the overview draft.

    Not Jira's own startOfWeek(): that follows each Jira user's locale
    setting, which would quietly make the page's answer depend on whose
    API token is configured.
    """
    return today - timedelta(days=today.weekday())


@dataclass(frozen=True)
class WorkloadReport:
    person: Person
    issues: list[Issue] = field(default_factory=list)
    # Finished work, passed in separately rather than mixed into `issues`:
    # every other view here (the ticket count, the project allocation, the
    # backlog) means *open* work, and folding completed tickets into that
    # list would silently change all of them.
    done_issues: list[Issue] = field(default_factory=list)

    @property
    def allocation_by_project(self) -> dict[str, float]:
        """What % of this person's open issues sit in each project.

        A quick way to answer "how split is this person across projects
        right now" without needing story points or logged hours.
        """
        if not self.issues:
            return {}
        counts: dict[str, int] = {}
        for issue in self.issues:
            counts[issue.project_key] = counts.get(issue.project_key, 0) + 1
        total = len(self.issues)
        return {project: round(count / total * 100, 1) for project, count in counts.items()}

    # cached_property, not property: `backlog_issues` reads `active_issues`,
    # and the workload page's three presenters (table, Gantt, markdown
    # overview) each read both of them more than once — which re-ran this
    # filter-and-sort ~8 times per member per request. cached_property
    # writes straight into the instance __dict__, so it works on a frozen
    # dataclass (no __setattr__ involved) as long as there are no __slots__.
    @cached_property
    def active_issues(self) -> list[Issue]:
        """Issues actually being worked or reviewed right now — what needs
        attention today. Ones being worked come first, then those in
        review; within each, soonest due date first (undated last).
        """
        matches = [
            issue
            for issue in self.issues
            if any(keyword in issue.status.name.lower() for keyword in _ACTIVE_STATUS_KEYWORDS)
        ]
        return sorted(matches, key=lambda issue: (is_reviewing(issue), issue.due_date is None, issue.due_date))

    @cached_property
    def completed_issues(self) -> list[Issue]:
        """Finished work, most recently completed first.

        Whoever built the report decided which window "finished" covers
        (the workload page asks for this week); this only orders it.
        Tickets with no completion timestamp sort last rather than
        blowing up the comparison.
        """
        dated = [issue for issue in self.done_issues if issue.completed_at is not None]
        undated = [issue for issue in self.done_issues if issue.completed_at is None]
        dated.sort(key=lambda issue: issue.completed_at, reverse=True)
        return dated + undated

    @cached_property
    def backlog_issues(self) -> list[Issue]:
        """Everything not currently active — queued, pending, or otherwise
        not yet being worked on.
        """
        active_keys = {issue.key for issue in self.active_issues}
        return [issue for issue in self.issues if issue.key not in active_keys]


class WorkloadReportService:
    """Depends only on the two Protocols it needs — not a concrete client."""

    def __init__(
        self,
        issue_repository: IssueRepository,
        person_repository: PersonRepository,
    ) -> None:
        self._issues = issue_repository
        self._person_resolver = PersonResolver(person_repository)

    def build_report(self, name_query: str) -> WorkloadReport:
        person = self._person_resolver.resolve(name_query)
        return self.build_report_for_person(person)

    def build_report_for_person(self, person: Person) -> WorkloadReport:
        """Skips name resolution entirely — for callers (e.g. a saved member
        roster) that already have a resolved Person on hand.
        """
        issues = self._issues.find_open_issues_for_assignee(person.account_id)
        return WorkloadReport(person=person, issues=issues)

    def build_reports_for_people(
        self, people: list[Person], completed_since: date | None = None
    ) -> list[WorkloadReport]:
        """One report per person — e.g. the whole member roster at once,
        so a page can show everyone's workload without picking a person first.

        Uses the batch port method rather than looping over
        `build_report_for_person`: that loop cost one sequential tracker
        query per member, which was the bulk of the workload and risk
        pages' load time.

        `completed_since` is opt-in because it costs a second tracker
        query: callers that only care about open work (the risk page) pay
        nothing for the finished-work list they would not render.
        """
        account_ids = [person.account_id for person in people]
        issues_by_account = self._issues.find_open_issues_for_assignees(account_ids)
        done_by_account = (
            self._issues.find_done_issues_for_assignees(account_ids, completed_since)
            if completed_since is not None
            else {}
        )
        return [
            WorkloadReport(
                person=person,
                issues=issues_by_account.get(person.account_id, []),
                done_issues=done_by_account.get(person.account_id, []),
            )
            for person in people
        ]
