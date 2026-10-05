"""Shared fixtures for the test suite."""
from __future__ import annotations

import os
from datetime import date, datetime, timezone

import pytest

from work_radar.domain.models import Issue, Person, Status, StatusCategory

# Pin the Jira settings before anything imports a presenter.
#
# A few presenters build issue URLs through JiraConfig.from_env(), so
# without this the suite could only run on a machine that already had a
# real .env — 29 tests failed with a bare ConfigurationError that named no
# cause, and two more asserted on one specific company's Jira host and so
# failed on anyone else's credentials.
#
# Assigned, not setdefault: config.py's own .env loader uses setdefault, so
# a real environment variable already wins over the file. Setting these
# outright is what makes the suite identical on every machine — with a
# .env, without one, and with someone else's. No test reaches the network,
# so the values only have to be well-formed, not real.
os.environ["JIRA_EMAIL"] = "tests@example.com"
os.environ["JIRA_API_TOKEN"] = "test-token"
os.environ["JIRA_DOMAIN"] = _TEST_JIRA_DOMAIN = "example.atlassian.net"

# The weekly overview's project ordering is deployment configuration with
# no default (the keys name one organisation's projects), so the suite
# supplies its own rather than asserting against whatever a developer
# happens to have in .env.
os.environ["OVERVIEW_PROJECT_RANK"] = "ABC,DEF,GHI"
os.environ["AUDIT_PROJECT_KEYS"] = "ABC"


@pytest.fixture
def jira_domain() -> str:
    """The host the suite pins above, for tests that assert on issue URLs."""
    return _TEST_JIRA_DOMAIN


@pytest.fixture
def make_issue():
    """Builds an Issue with sane defaults so each test only states what it
    actually cares about.
    """

    def _make_issue(
        key: str,
        *,
        status_name: str = "Open",
        status_category: StatusCategory = StatusCategory.TODO,
        updated_at: datetime = datetime(2026, 1, 1, tzinfo=timezone.utc),
        created_at: datetime = datetime(2025, 12, 1, tzinfo=timezone.utc),
        assignee: Person | None = None,
        summary: str | None = None,
        project_key: str = "GHI",
        issue_type: str = "Task",
        start_date: date | None = None,
        due_date: date | None = None,
        completed_at: datetime | None = None,
        priority: str | None = None,
        labels: tuple[str, ...] = (),
    ) -> Issue:
        return Issue(
            key=key,
            summary=summary or f"Summary for {key}",
            status=Status(name=status_name, category=status_category),
            project_key=project_key,
            issue_type=issue_type,
            updated_at=updated_at,
            created_at=created_at,
            assignee=assignee,
            start_date=start_date,
            due_date=due_date,
            completed_at=completed_at,
            priority=priority,
            labels=labels,
        )

    return _make_issue
