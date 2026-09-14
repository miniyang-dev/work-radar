"""Unit tests for weekly_overview_markdown — the "Ongoing Project" draft.

Uses the real presenters module, which builds issue URLs from the Jira
settings conftest pins for the whole suite — take the `jira_domain` fixture
rather than writing a host into an assertion.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from work_radar.application.workload_report import WorkloadReport
from work_radar.domain.models import Person
from work_radar.web.presenters import weekly_overview_markdown


def test_overview_skips_members_with_no_active_issues(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    report = WorkloadReport(person=alice, issues=[make_issue("GHI-1", status_name="Pending")])

    markdown = weekly_overview_markdown([report])

    assert "Alice Wu" not in markdown


def test_overview_groups_by_member_and_orders_by_project_then_due_date(make_issue):
    """Project order is conftest's OVERVIEW_PROJECT_RANK (ABC,DEF,GHI),
    not a constant in the code — it names real projects, so it moved to
    configuration.
    """
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    de_issue = make_issue("GHI-1", status_name="Running", project_key="GHI", due_date=date(2026, 9, 1))
    tse_issue = make_issue("ABC-1", status_name="Running", project_key="ABC", due_date=date(2026, 9, 10))
    trn_issue = make_issue("DEF-1", status_name="Running", project_key="DEF", due_date=date(2026, 9, 5))
    report = WorkloadReport(person=alice, issues=[de_issue, trn_issue, tse_issue])

    markdown = weekly_overview_markdown([report])

    tse_pos = markdown.index("ABC-1")
    trn_pos = markdown.index("DEF-1")
    de_pos = markdown.index("GHI-1")
    assert tse_pos < trn_pos < de_pos


def test_overview_orders_projects_of_the_same_rank_by_due_date(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    later = make_issue("ABC-1", status_name="Running", project_key="ABC", due_date=date(2026, 9, 20))
    sooner = make_issue("ABC-2", status_name="Running", project_key="ABC", due_date=date(2026, 9, 5))
    report = WorkloadReport(person=alice, issues=[later, sooner])

    markdown = weekly_overview_markdown([report])

    assert markdown.index("ABC-2") < markdown.index("ABC-1")


def test_overview_line_shows_day_count_and_done_date(make_issue, jira_domain):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    issue = make_issue(
        "ABC-1",
        status_name="Running",
        project_key="ABC",
        created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        due_date=date(2026, 8, 11),
    )
    report = WorkloadReport(person=alice, issues=[issue])

    markdown = weekly_overview_markdown([report])

    assert f"- https://{jira_domain}/browse/ABC-1" in markdown
    assert "   - 人力:10天,完成日:2026-08-11" in markdown
    assert "1. https://" not in markdown


def test_overview_header_is_immediately_followed_by_the_member_name(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    issue = make_issue("ABC-1", status_name="Running")
    report = WorkloadReport(person=alice, issues=[issue])

    markdown = weekly_overview_markdown([report])

    assert "Ongoing Project\nAlice Wu\n" in markdown


def test_overview_omits_the_labor_line_entirely_when_due_date_is_missing(make_issue, jira_domain):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    issue = make_issue("ABC-1", status_name="Running", project_key="ABC", due_date=None)
    report = WorkloadReport(person=alice, issues=[issue])

    markdown = weekly_overview_markdown([report])

    assert "人力" not in markdown
    assert f"https://{jira_domain}/browse/ABC-1" in markdown


def test_overview_has_no_priority_order_suffix_in_the_header(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    issue = make_issue("ABC-1", status_name="Running")
    markdown = weekly_overview_markdown([WorkloadReport(person=alice, issues=[issue])])

    assert markdown.startswith("Ongoing Project\n")
    assert "以下順序為優先順序" not in markdown


def test_overview_ends_with_the_last_members_tickets(make_issue):
    """There is no sign-off line: the draft ends where the content does,
    and whoever sends it adds their own closing.
    """
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    issue = make_issue("ABC-1", status_name="Running")
    markdown = weekly_overview_markdown([WorkloadReport(person=alice, issues=[issue])])

    assert markdown.strip().endswith("/browse/ABC-1")


def test_overview_prepends_the_saved_intro_note_when_given(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    issue = make_issue("ABC-1", status_name="Running")
    report = WorkloadReport(person=alice, issues=[issue])

    markdown = weekly_overview_markdown([report], intro="本季重點方向：\n第一項、第二項")

    assert markdown.startswith("本季重點方向：\n第一項、第二項\n\nOngoing Project")


def test_overview_skips_intro_block_when_blank(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    issue = make_issue("ABC-1", status_name="Running")
    report = WorkloadReport(person=alice, issues=[issue])

    markdown = weekly_overview_markdown([report], intro="   ")

    assert markdown.startswith("Ongoing Project")
