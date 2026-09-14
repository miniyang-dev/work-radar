"""Tests for the Jira repository adapters against a recording fake HTTP client.

Covers the parts of the adapter that are easy to get subtly wrong and
invisible from the outside: how user input is encoded into request paths
and JQL, when the parent-link fallback kicks in, and that the batch
methods really do collapse into a single request.
"""
from __future__ import annotations

import logging

import pytest

from work_radar.domain.exceptions import IssueNotFoundError
from work_radar.infrastructure.jira.errors import JiraApiError
from work_radar.infrastructure.jira.repositories import (
    JiraIssueHistoryRepository,
    JiraIssueRepository,
)


def _raw_issue(key: str, *, account_id: str | None = None, project_key: str = "GHI") -> dict:
    assignee = {"accountId": account_id, "displayName": f"Person {account_id}"} if account_id else None
    return {
        "key": key,
        "fields": {
            "summary": f"Summary for {key}",
            "status": {"name": "Running", "statusCategory": {"key": "indeterminate"}},
            "project": {"key": project_key},
            "issuetype": {"name": "Task"},
            "updated": "2026-09-04T16:37:10.968+0800",
            "created": "2026-01-01T09:00:00.000+0800",
            "assignee": assignee,
        },
    }


class FakeHttpClient:
    """Records every (path, params) and replays queued responses.

    `responses` is either a list consumed in order, or a callable taking
    (path, params).
    """

    def __init__(self, responses) -> None:
        self._responses = responses
        self.calls: list[tuple[str, dict]] = []

    def get(self, path, params=None):
        self.calls.append((path, params or {}))
        if callable(self._responses):
            return self._responses(path, params or {})
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    @property
    def paths(self) -> list[str]:
        return [path for path, _ in self.calls]

    def jqls(self) -> list[str]:
        return [params["jql"] for _, params in self.calls if "jql" in params]


# --- request-path encoding -------------------------------------------------


def test_issue_key_is_url_encoded_into_the_request_path():
    """An unencoded key with `/` or `..` retargets the call at a different
    endpoint, because requests normalises the path before sending it.
    """
    http = FakeHttpClient([_raw_issue("GHI-1")])
    JiraIssueRepository(http).get_issue("GHI-1/../../../3/myself")

    path = http.paths[0]
    assert path == "/rest/api/3/issue/GHI-1%2F..%2F..%2F..%2F3%2Fmyself"
    assert path.count("/rest/api/3/issue/") == 1


def test_get_issue_translates_404_into_a_domain_error():
    http = FakeHttpClient([JiraApiError(404, "not found")])
    with pytest.raises(IssueNotFoundError):
        JiraIssueRepository(http).get_issue("GHI-404")


# --- JQL escaping ----------------------------------------------------------


def test_project_keys_are_quoted_in_jql():
    http = FakeHttpClient([{"issues": [], "isLast": True}])
    JiraIssueRepository(http).find_open_issues_for_projects(["GHI", "ABC"])

    assert 'project in ("GHI", "ABC")' in http.jqls()[0]


def test_issues_created_since_windows_on_creation_and_keeps_done_rows():
    """The audit asks "what came in this quarter", which an `updated`
    window answers wrongly — it drags in year-old tickets touched
    yesterday and misses new ones nobody has edited since.
    """
    http = FakeHttpClient([{"issues": [], "isLast": True}])
    JiraIssueRepository(http).find_issues_created_since_for_projects(["ABC"], 90)

    jql = http.jqls()[0]
    assert jql == 'project in ("ABC") AND created >= -90d ORDER BY created DESC'
    assert "statusCategory" not in jql


def test_a_created_window_cannot_smuggle_jql_through_the_day_count():
    http = FakeHttpClient([{"issues": [], "isLast": True}])
    JiraIssueRepository(http).find_issues_created_since_for_projects(['ABC" OR project = SECRET'], 90)

    jql = http.jqls()[0]
    assert jql.startswith('project in ("ABC\\" OR project = SECRET")')


def test_a_quote_in_a_value_cannot_break_out_of_its_jql_literal():
    http = FakeHttpClient([{"issues": [], "isLast": True}])
    JiraIssueRepository(http).find_open_issues_for_assignee('acc" OR project = SECRET')

    jql = http.jqls()[0]
    assert jql.startswith('assignee = "acc\\" OR project = SECRET"')
    assert "AND statusCategory != Done" in jql


# --- parent-link fallback --------------------------------------------------


def test_find_children_falls_through_to_epic_link_on_an_empty_result():
    """A company-managed project answers `parent = KEY` successfully with
    zero rows, so stopping at the first success reported such Epics as
    childless.
    """
    http = FakeHttpClient(
        [
            {"issues": [], "isLast": True},
            {"issues": [_raw_issue("GHI-2")], "isLast": True},
        ]
    )

    children = JiraIssueRepository(http).find_children("GHI-1")

    assert [child.key for child in children] == ["GHI-2"]
    assert 'parent = "GHI-1"' in http.jqls()[0]
    assert '"Epic Link" = "GHI-1"' in http.jqls()[1]


def test_find_children_stops_at_the_first_non_empty_result():
    http = FakeHttpClient([{"issues": [_raw_issue("GHI-2")], "isLast": True}])

    children = JiraIssueRepository(http).find_children("GHI-1")

    assert [child.key for child in children] == ["GHI-2"]
    assert len(http.calls) == 1


def test_find_children_returns_empty_when_both_conventions_are_empty():
    http = FakeHttpClient([{"issues": [], "isLast": True}, {"issues": [], "isLast": True}])
    assert JiraIssueRepository(http).find_children("GHI-1") == []


def test_find_children_raises_when_every_convention_errors():
    """Previously guarded by a bare `assert`, which `python -O` strips."""
    http = FakeHttpClient([JiraApiError(400, "no parent field"), JiraApiError(400, "no Epic Link field")])

    with pytest.raises(JiraApiError):
        JiraIssueRepository(http).find_children("GHI-1")


# --- batch fetching -------------------------------------------------------


def test_open_issues_for_assignees_uses_one_search_and_groups_by_person():
    http = FakeHttpClient(
        [
            {
                "issues": [
                    _raw_issue("GHI-1", account_id="acc-1"),
                    _raw_issue("GHI-2", account_id="acc-2"),
                    _raw_issue("GHI-3", account_id="acc-1"),
                ],
                "isLast": True,
            }
        ]
    )

    grouped = JiraIssueRepository(http).find_open_issues_for_assignees(["acc-1", "acc-2", "acc-3"])

    assert len(http.calls) == 1, "one query for the whole roster, not one per person"
    assert [issue.key for issue in grouped["acc-1"]] == ["GHI-1", "GHI-3"]
    assert [issue.key for issue in grouped["acc-2"]] == ["GHI-2"]
    assert grouped["acc-3"] == [], "a person with nothing open still gets an entry"


def test_open_issues_for_assignees_makes_no_request_for_an_empty_roster():
    http = FakeHttpClient([])
    assert JiraIssueRepository(http).find_open_issues_for_assignees([]) == {}
    assert http.calls == []


def test_transitions_for_issues_reads_the_changelog_embedded_in_one_search():
    embedded = {
        "issues": [
            {
                "key": "GHI-1",
                "changelog": {
                    "histories": [
                        {
                            "created": "2026-09-01T10:00:00.000+0800",
                            "items": [{"field": "status", "fromString": "Submitted", "toString": "Running"}],
                        }
                    ]
                },
            }
        ],
        "isLast": True,
    }
    http = FakeHttpClient([embedded])

    transitions = JiraIssueHistoryRepository(http).get_transitions_for_issues(["GHI-1"])

    assert len(http.calls) == 1, "one search, not one changelog request per issue"
    assert [t.to_status for t in transitions["GHI-1"]] == ["Running"]


def test_transitions_for_issues_falls_back_when_the_search_omits_the_changelog():
    """A deployment that ignores `expand=changelog` must cost speed, not
    silently report every issue as having no history.
    """

    def respond(path, params):
        if path == "/rest/api/3/search/jql":
            return {"issues": [{"key": "GHI-1"}], "isLast": True}
        return {
            "values": [
                {
                    "created": "2026-09-02T10:00:00.000+0800",
                    "items": [{"field": "status", "fromString": "Running", "toString": "Done"}],
                }
            ],
            "total": 1,
        }

    http = FakeHttpClient(respond)

    transitions = JiraIssueHistoryRepository(http).get_transitions_for_issues(["GHI-1"])

    assert [t.to_status for t in transitions["GHI-1"]] == ["Done"]
    assert "/rest/api/3/issue/GHI-1/changelog" in http.paths


def test_transitions_for_issues_makes_no_request_for_an_empty_batch():
    http = FakeHttpClient([])
    assert JiraIssueHistoryRepository(http).get_transitions_for_issues([]) == {}
    assert http.calls == []


# --- truncation ------------------------------------------------------------


def test_hitting_the_search_page_cap_logs_a_warning(caplog):
    """Silently returning a truncated result set makes a report under-count
    with nothing to show it happened.
    """
    http = FakeHttpClient(lambda path, params: {"issues": [], "nextPageToken": "more", "isLast": False})

    with caplog.at_level(logging.WARNING):
        JiraIssueRepository(http).find_open_issues_for_projects(["GHI"])

    assert "truncated" in caplog.text
