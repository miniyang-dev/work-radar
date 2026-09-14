"""Adapters that implement the domain ports against the Jira REST API.

These classes satisfy IssueRepository/IssueHistoryRepository/PersonRepository
by structural typing alone (no inheritance needed) — that's what lets
application services stay ignorant of Jira entirely.
"""
from __future__ import annotations

import logging
from datetime import date
from urllib.parse import quote

from work_radar.domain.exceptions import IssueNotFoundError
from work_radar.domain.models import Comment, Issue, Person, StatusCategory, StatusTransition
from work_radar.infrastructure.jira.errors import JiraApiError
from work_radar.infrastructure.jira.http import JiraHttpClient
from work_radar.infrastructure.jira.mappers import (
    START_DATE_FIELD,
    STATUS_CATEGORY_CHANGED_FIELD,
    to_comments,
    to_issue,
    to_person,
    to_status_catalog,
    to_transitions,
)

logger = logging.getLogger(__name__)

_ISSUE_FIELDS = (
    "summary,status,assignee,priority,updated,created,duedate,project,issuetype,parent"
    f",{START_DATE_FIELD},{STATUS_CATEGORY_CHANGED_FIELD}"
)
_SEARCH_PAGE_SIZE = 100
_MAX_SEARCH_PAGES = 20  # safety cap: 2,000 issues per query is already a lot for this tool's scope

# How many issue keys to put in one `key in (...)` JQL clause. Keeps the
# query string well clear of Jira's URL length limit while still collapsing
# a whole weekly window into one or two requests.
_KEY_BATCH_SIZE = 50

# Company-managed Jira projects still use the classic "Epic Link" field;
# team-managed projects use the newer "parent" field. Try both.
_CHILD_ISSUE_JQL_TEMPLATES = (
    "parent = {key}",
    '"Epic Link" = {key}',
)


def _jql_string(value: str) -> str:
    """Renders a value as a quoted JQL string literal.

    Interpolating raw values into JQL lets a stray quote (or a deliberately
    crafted project key / account id, both of which reach here from user
    input) change the meaning of the query. JQL escapes with backslashes
    inside double quotes, so both characters need doubling up.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _jql_list(values: list[str]) -> str:
    return ", ".join(_jql_string(value) for value in values)


def _path_segment(value: str) -> str:
    """URL-encodes a single path segment.

    An unencoded issue key is interpolated straight into the request path,
    so a key containing `/` or `..` silently retargets the call at a
    different endpoint (requests normalises the path before sending it).
    """
    return quote(value, safe="")


class JiraIssueRepository:
    def __init__(self, http_client: JiraHttpClient) -> None:
        self._http = http_client

    def get_issue(self, key: str) -> Issue:
        try:
            raw = self._http.get(
                f"/rest/api/3/issue/{_path_segment(key)}",
                params={"fields": _ISSUE_FIELDS},
            )
        except JiraApiError as error:
            if error.status_code == 404:
                raise IssueNotFoundError(key) from error
            raise
        return to_issue(raw)

    def find_children(self, parent_key: str) -> list[Issue]:
        """Tries both parent-link conventions, falling through on an *empty*
        result as well as on an error.

        A company-managed project answers `parent = KEY` successfully but
        with zero rows (its hierarchy lives in "Epic Link" instead), so
        stopping at the first successful query silently reported such Epics
        as childless. The cost is one extra request for issues that
        genuinely have no children.
        """
        last_error: JiraApiError | None = None
        for template in _CHILD_ISSUE_JQL_TEMPLATES:
            try:
                children = self._search(template.format(key=_jql_string(parent_key)))
            except JiraApiError as error:
                last_error = error
                continue
            if children:
                return children

        if last_error is not None:
            raise last_error
        return []

    def find_open_issues_for_assignee(self, account_id: str) -> list[Issue]:
        jql = f"assignee = {_jql_string(account_id)} AND statusCategory != Done ORDER BY updated DESC"
        return self._search(jql)

    def find_open_issues_for_assignees(self, account_ids: list[str]) -> dict[str, list[Issue]]:
        """Every listed person's open issues in one query, grouped by id.

        The per-person method above needs one round-trip per person, which
        is what made the roster-wide pages (workload, risk) take N
        sequential Jira searches to render. One `assignee in (...)` query
        returns the same rows in one.
        """
        if not account_ids:
            return {}

        grouped: dict[str, list[Issue]] = {account_id: [] for account_id in account_ids}
        known_ids = set(account_ids)

        for batch in _chunked(account_ids, _KEY_BATCH_SIZE):
            jql = f"assignee in ({_jql_list(batch)}) AND statusCategory != Done ORDER BY updated DESC"
            for issue in self._search(jql):
                # An issue can only come back here because of its assignee,
                # but guard anyway rather than risk a KeyError on a row Jira
                # returned for a reason we didn't ask about.
                if issue.assignee is not None and issue.assignee.account_id in known_ids:
                    grouped[issue.assignee.account_id].append(issue)

        return grouped

    def find_done_issues_for_assignees(
        self, account_ids: list[str], since: date
    ) -> dict[str, list[Issue]]:
        """Batched like `find_open_issues_for_assignees`, and for the same
        reason — one query for the whole roster instead of one per member.

        Filters on statusCategoryChangedDate rather than `updated` or
        `resolutiondate`: `updated` also matches tickets merely touched
        this week, and `resolutiondate` is empty on any workflow that
        reaches Done without setting a resolution (several here do).
        """
        if not account_ids:
            return {}

        grouped: dict[str, list[Issue]] = {account_id: [] for account_id in account_ids}
        known_ids = set(account_ids)

        for batch in _chunked(account_ids, _KEY_BATCH_SIZE):
            jql = (
                f"assignee in ({_jql_list(batch)}) AND statusCategory = Done "
                f"AND statusCategoryChangedDate >= {_jql_string(since.isoformat())} "
                "ORDER BY updated DESC"
            )
            for issue in self._search(jql):
                if issue.assignee is not None and issue.assignee.account_id in known_ids:
                    grouped[issue.assignee.account_id].append(issue)

        return grouped

    def find_open_issues_for_projects(self, project_keys: list[str]) -> list[Issue]:
        jql = f"project in ({_jql_list(project_keys)}) AND statusCategory != Done ORDER BY updated ASC"
        return self._search(jql)

    def find_done_issues_for_projects(self, project_keys: list[str], window_days: int) -> list[Issue]:
        jql = (
            f"project in ({_jql_list(project_keys)}) AND statusCategory = Done "
            f"AND updated >= -{int(window_days)}d ORDER BY updated DESC"
        )
        return self._search(jql)

    def find_issues_created_since_for_projects(
        self, project_keys: list[str], window_days: int
    ) -> list[Issue]:
        # No statusCategory filter, unlike every other project query here:
        # the audit needs the full intake for the window, and decides for
        # itself what to do with the closed ones.
        jql = (
            f"project in ({_jql_list(project_keys)}) AND created >= -{int(window_days)}d "
            f"ORDER BY created DESC"
        )
        return self._search(jql)

    def find_issues_updated_since_for_assignee(self, account_id: str, window_days: int) -> list[Issue]:
        jql = (
            f"assignee = {_jql_string(account_id)} AND updated >= -{int(window_days)}d "
            f"ORDER BY updated DESC"
        )
        return self._search(jql)

    def _search(self, jql: str) -> list[Issue]:
        """Pages through /search/jql via its cursor (nextPageToken) until
        the API reports isLast, up to a generous safety cap.
        """
        issues: list[Issue] = []
        next_page_token: str | None = None

        for _ in range(_MAX_SEARCH_PAGES):
            params = {"jql": jql, "fields": _ISSUE_FIELDS, "maxResults": _SEARCH_PAGE_SIZE}
            if next_page_token:
                params["nextPageToken"] = next_page_token

            result = self._http.get("/rest/api/3/search/jql", params=params)
            issues.extend(to_issue(raw) for raw in result.get("issues", []))

            next_page_token = result.get("nextPageToken")
            if result.get("isLast", True) or not next_page_token:
                break
        else:
            # Loop ran the full cap without the API saying it was done, so
            # the caller is holding a silently truncated result set. Say so
            # rather than let a report quietly under-report.
            logger.warning(
                "Hit the %d-page search cap (%d issues) for JQL %r — results are truncated.",
                _MAX_SEARCH_PAGES,
                len(issues),
                jql,
            )

        return issues


def _chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


class JiraIssueHistoryRepository:
    def __init__(self, http_client: JiraHttpClient) -> None:
        self._http = http_client

    def get_transitions(self, key: str) -> list[StatusTransition]:
        # Note: this endpoint nests history entries under "values", unlike
        # bulk search's expand=changelog which uses "histories" — see the
        # docstring on to_transitions().
        encoded_key = _path_segment(key)
        raw = self._http.get(f"/rest/api/3/issue/{encoded_key}/changelog", params={"maxResults": 100})
        values = raw.get("values", [])
        transitions = to_transitions(values)

        total = raw.get("total", len(values))
        start_at = len(values)
        while start_at < total:
            page = self._http.get(
                f"/rest/api/3/issue/{encoded_key}/changelog",
                params={"startAt": start_at, "maxResults": 100},
            )
            page_values = page.get("values", [])
            transitions.extend(to_transitions(page_values))
            if not page_values:
                break
            start_at += len(page_values)

        return transitions

    def get_transitions_for_issues(self, keys: list[str]) -> dict[str, list[StatusTransition]]:
        """Changelogs for many issues in one search instead of one request each.

        Bulk search's `expand=changelog` embeds each issue's history under
        `changelog.histories` — the second shape to_transitions() already
        handles — which collapses the weekly report's 1+N requests into
        one. That embedded copy only carries an issue's most recent history
        entries, which is fine for a days-long window but not for a full
        lead-time backfill; cycle-time therefore keeps using the paginated
        per-issue endpoint above.

        Any issue the search doesn't come back with changelog data for
        (an older Jira deployment ignoring the expand, a row dropped from
        the result) falls back to a single-issue fetch, so a missing expand
        costs speed rather than silently reporting an empty history.
        """
        if not keys:
            return {}

        transitions: dict[str, list[StatusTransition]] = {}
        for batch in _chunked(keys, _KEY_BATCH_SIZE):
            result = self._http.get(
                "/rest/api/3/search/jql",
                params={
                    "jql": f"key in ({_jql_list(batch)})",
                    "fields": "key",
                    "expand": "changelog",
                    "maxResults": len(batch),
                },
            )
            for raw in result.get("issues", []):
                changelog = raw.get("changelog")
                if not isinstance(changelog, dict) or "histories" not in changelog:
                    continue
                transitions[raw["key"]] = to_transitions(changelog["histories"])

        for key in keys:
            if key not in transitions:
                transitions[key] = self.get_transitions(key)

        return transitions


class JiraIssueCommentRepository:
    def __init__(self, http_client: JiraHttpClient) -> None:
        self._http = http_client

    def get_comments(self, key: str) -> list[Comment]:
        comments: list[Comment] = []
        start_at = 0

        while True:
            raw = self._http.get(
                f"/rest/api/3/issue/{_path_segment(key)}/comment",
                params={"startAt": start_at, "maxResults": 100},
            )
            values = raw.get("comments", [])
            comments.extend(to_comments(values))

            start_at += len(values)
            if not values or start_at >= raw.get("total", start_at):
                break

        return comments


class JiraStatusCatalogRepository:
    """Caches each project's status->category catalog for the process
    lifetime — a project's workflow rarely changes mid-session.
    """

    def __init__(self, http_client: JiraHttpClient) -> None:
        self._http = http_client
        self._cache: dict[str, dict[str, StatusCategory]] = {}

    def get_status_catalog(self, project_key: str) -> dict[str, StatusCategory]:
        if project_key not in self._cache:
            raw_issue_types = self._http.get(f"/rest/api/3/project/{_path_segment(project_key)}/statuses")
            self._cache[project_key] = to_status_catalog(raw_issue_types)
        return self._cache[project_key]


class JiraPersonRepository:
    def __init__(self, http_client: JiraHttpClient) -> None:
        self._http = http_client

    def find_by_name(self, query: str) -> list[Person]:
        raw_users = self._http.get("/rest/api/3/user/search", params={"query": query})
        return [to_person(raw) for raw in raw_users]
