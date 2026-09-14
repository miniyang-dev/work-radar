"""Tests for the ABC audit page's view model."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from work_radar.application.project_audit import ProjectAuditService
from work_radar.domain.models import Person, StatusCategory
from work_radar.web.presenters import normalize_group_by, project_audit_view

AS_OF = datetime(2026, 9, 9, tzinfo=timezone.utc)
FRESH = datetime(2026, 9, 8, tzinfo=timezone.utc)


class FakeIssues:
    def __init__(self, issues):
        self._issues = list(issues)

    def find_issues_created_since_for_projects(self, project_keys, window_days):
        return list(self._issues)


@pytest.fixture(autouse=True)
def jira_domain(monkeypatch):
    """issue_row() builds browse URLs, which reach for JiraConfig."""
    monkeypatch.setattr("work_radar.web.presenters._jira_domain", lambda: "example.atlassian.net")


@pytest.fixture
def report(make_issue):
    alice = Person(account_id="a", display_name="Alice Wu")
    hsin = Person(account_id="b", display_name="Bob Lin")
    issues = [
        make_issue("ABC-1", priority="P0", issue_type="Bug", assignee=alice, updated_at=FRESH),
        make_issue("ABC-2", priority="P2", issue_type="Task", assignee=hsin, updated_at=FRESH),
        make_issue("ABC-3", priority="P2", issue_type="Bug", assignee=alice, updated_at=FRESH),
        make_issue(
            "ABC-4",
            status_name="Done",
            status_category=StatusCategory.DONE,
            issue_type="Task",
            updated_at=FRESH,
        ),
    ]
    return ProjectAuditService(FakeIssues(issues)).build_report(
        ["ABC"], window_days=90, as_of=AS_OF
    )


def test_ungrouped_is_a_single_unnamed_group(report):
    """One shape for both modes, so the template renders the same table
    markup whether or not grouping is on.
    """
    view = project_audit_view(report, "none")

    assert view["grouped"] is False
    (group,) = view["groups"]
    assert group["title"] is None
    assert [row["key"] for row in group["rows"]] == ["ABC-1", "ABC-2", "ABC-3"]


def test_grouping_by_assignee_puts_the_most_urgent_person_first(report):
    view = project_audit_view(report, "assignee")

    assert view["grouped"] is True
    assert [group["title"] for group in view["groups"]] == ["Alice Wu", "Bob Lin"]
    assert view["groups"][0]["avatar"]["initials"] == "AW"


def test_grouping_by_type_orders_groups_by_their_worst_row(report):
    view = project_audit_view(report, "type")

    assert [group["title"] for group in view["groups"]] == ["Bug", "Task"]
    assert [row["key"] for row in view["groups"][0]["rows"]] == ["ABC-1", "ABC-3"]
    assert view["groups"][0]["avatar"] is None


def test_a_hand_edited_group_by_falls_back_instead_of_failing(report):
    view = project_audit_view(report, "by-vibes")

    assert view["group_by"] == "none"
    assert normalize_group_by(None) == "none"


def test_rows_explain_their_own_urgency(make_issue):
    """A bare score nobody can audit is worse than no score at all."""
    issues = [make_issue("ABC-1", priority="P1", due_date=date(2026, 9, 4), updated_at=FRESH)]
    report = ProjectAuditService(FakeIssues(issues)).build_report(
        ["ABC"], window_days=90, as_of=AS_OF
    )

    (row,) = project_audit_view(report)["groups"][0]["rows"]

    assert row["urgency_label"] == "危急"
    assert row["urgency_css"] == "urgency-critical"
    assert "逾期 5 天" in row["urgency_reasons"]
    assert "P1" in row["urgency_reasons"]
    assert row["is_overdue"] is True
    # created_at is new on issue_row — the audit table shows it as a column.
    assert row["created_at"] == "2025-12-01"


def test_done_issues_are_kept_out_of_the_ranked_groups(report):
    view = project_audit_view(report)

    assert [row["key"] for row in view["done"]] == ["ABC-4"]
    assert "ABC-4" not in [row["key"] for group in view["groups"] for row in group["rows"]]


def test_gaps_reach_the_page_as_counts_not_as_a_second_copy_of_the_list(make_issue):
    """Every open ABC issue lands in at least one gap bucket on real data
    (no_due_date has been 100% of the open queue at every window), so
    rendering the buckets as tables reprinted the ranked list below them.
    """
    issues = [make_issue("ABC-1", updated_at=datetime(2026, 7, 1, tzinfo=timezone.utc))]
    report = ProjectAuditService(FakeIssues(issues)).build_report(
        ["ABC"], window_days=90, as_of=AS_OF, stale_days=14
    )

    view = project_audit_view(report)

    assert "gaps" not in view
    assert view["stats"]["no_due_date_count"] == 1
    assert view["stats"]["unassigned_count"] == 1
    assert view["stats"]["stale_count"] == 1
    # The 待處理門檻 control has nothing else left to drive, so the page
    # has to be able to label the count with the threshold it used.
    assert view["stats"]["stale_days"] == 14


def test_an_empty_window_renders_no_groups(make_issue):
    report = ProjectAuditService(FakeIssues([])).build_report(
        ["ABC"], window_days=90, as_of=AS_OF
    )

    view = project_audit_view(report)

    assert view["groups"] == []
    assert view["stats"]["total"] == 0
    assert view["stats"]["done_rate"] == 0
