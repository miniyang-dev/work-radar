"""Abstract boundaries the application layer depends on.

These are the seam the Dependency Inversion Principle asks for: application
services import only these Protocols, never a concrete adapter. Any class
that implements the right methods satisfies a Protocol automatically
(structural typing) — an adapter doesn't need to inherit from it.

Split into small, single-purpose interfaces (Interface Segregation) so a
consumer that only reads issue lists isn't forced to depend on changelog
access or person lookup, and vice versa.
"""
from __future__ import annotations

from datetime import date
from typing import Protocol

from work_radar.domain.models import (
    Comment,
    Issue,
    Person,
    StatusCategory,
    StatusTransition,
    TrackingItem,
)


class IssueRepository(Protocol):
    """Read access to issues and their hierarchy."""

    def get_issue(self, key: str) -> Issue:
        ...

    def find_children(self, parent_key: str) -> list[Issue]:
        ...

    def find_open_issues_for_assignee(self, account_id: str) -> list[Issue]:
        ...

    def find_open_issues_for_assignees(self, account_ids: list[str]) -> dict[str, list[Issue]]:
        """The same as above for many people at once, keyed by account id.

        Exists so a roster-wide page doesn't need one round-trip per
        person. Every listed id must appear in the result, mapped to an
        empty list when that person has nothing open.
        """
        ...

    def find_done_issues_for_assignees(
        self, account_ids: list[str], since: date
    ) -> dict[str, list[Issue]]:
        """Issues each listed person finished on or after `since`, keyed by
        account id.

        Keyed on when the issue reached the Done category, not on when it
        was last updated — a ticket closed last month and commented on
        today is not this week's work. Every listed id must appear in the
        result, mapped to an empty list when that person finished nothing.
        """
        ...

    def find_open_issues_for_projects(self, project_keys: list[str]) -> list[Issue]:
        ...

    def find_done_issues_for_projects(self, project_keys: list[str], window_days: int) -> list[Issue]:
        ...

    def find_issues_created_since_for_projects(
        self, project_keys: list[str], window_days: int
    ) -> list[Issue]:
        """Every issue *opened* in those projects during the window.

        The only window here keyed on creation rather than activity: a
        project audit asks "what came in this quarter", which a
        `updated >= -Nd` query answers wrongly (it drags in year-old
        tickets that happened to be touched yesterday, and misses new
        ones nobody has edited since). Done issues are included — the
        audit reports the whole intake, not just what's left.
        """
        ...

    def find_issues_updated_since_for_assignee(self, account_id: str, window_days: int) -> list[Issue]:
        ...


class IssueHistoryRepository(Protocol):
    """Read access to an issue's status-transition history."""

    def get_transitions(self, key: str) -> list[StatusTransition]:
        ...

    def get_transitions_for_issues(self, keys: list[str]) -> dict[str, list[StatusTransition]]:
        """Transitions for many issues at once, keyed by issue key.

        Same contract as above per issue, but lets an adapter fetch a whole
        batch in one call instead of one request per issue. Every requested
        key must appear in the result, mapped to an empty list when that
        issue has no status history.
        """
        ...


class IssueCommentRepository(Protocol):
    """Read access to an issue's comments."""

    def get_comments(self, key: str) -> list[Comment]:
        ...


class StatusCatalogRepository(Protocol):
    """Maps a project's status *names* to their category.

    Needed because changelog transitions carry only a status name (e.g.
    "Running / 執行中"), never its category — this is the only source that
    reliably covers every status a project's workflow defines, regardless
    of which statuses happen to appear on issues fetched elsewhere.
    """

    def get_status_catalog(self, project_key: str) -> dict[str, StatusCategory]:
        ...


class PersonRepository(Protocol):
    """Read access to people/assignees."""

    def find_by_name(self, query: str) -> list[Person]:
        ...


class MemberRepository(Protocol):
    """Read/write access to work-radar's own curated roster of people.

    Distinct from PersonRepository (a live, ad-hoc Jira user search): a
    roster member is added once — via a Jira lookup — and then reused
    everywhere a name would otherwise need to be typed and re-resolved.
    `add_member` upserts by `account_id`, so re-adding also renames.
    """

    def list_members(self) -> list[Person]:
        ...

    def add_member(self, person: Person) -> None:
        ...

    def remove_member(self, account_id: str) -> None:
        ...


class TrackingItemRepository(Protocol):
    """Read/write access to the hand-kept follow-up list.

    Nothing here talks to a tracker — these items exist only inside
    work-radar, which is what lets the page work with no Jira credentials
    at all. `save` upserts by `id` (the same contract as
    MemberRepository.add_member) and `delete` on an unknown id is a no-op
    rather than an error, so a double-submitted form can't fail.
    """

    def list_items(self) -> list[TrackingItem]:
        ...

    def save(self, item: TrackingItem) -> None:
        ...

    def delete(self, item_id: str) -> None:
        ...
