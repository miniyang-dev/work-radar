"""Unit tests for WorkloadReportService, using in-memory fakes for the ports.

The fakes satisfy IssueRepository/PersonRepository purely by having the
right methods (structural typing) — no test double library needed.
"""
from __future__ import annotations

import pytest

from datetime import date, datetime, timezone

from work_radar.application.workload_report import (
    WorkloadReport,
    WorkloadReportService,
    start_of_week,
)
from work_radar.domain.exceptions import AmbiguousPersonError, PersonNotFoundError
from work_radar.domain.models import Person, StatusCategory


class FakeIssueRepository:
    def __init__(self, issues_by_account: dict, done_by_account: dict | None = None) -> None:
        self._issues_by_account = issues_by_account
        self._done_by_account = done_by_account or {}
        self.batch_calls = 0
        self.done_queries: list[date] = []

    def get_issue(self, key):
        raise NotImplementedError("not needed for these tests")

    def find_children(self, parent_key):
        raise NotImplementedError("not needed for these tests")

    def find_open_issues_for_assignee(self, account_id):
        return self._issues_by_account.get(account_id, [])

    def find_open_issues_for_assignees(self, account_ids):
        self.batch_calls += 1
        return {account_id: self._issues_by_account.get(account_id, []) for account_id in account_ids}

    def find_done_issues_for_assignees(self, account_ids, since):
        self.done_queries.append(since)
        return {account_id: self._done_by_account.get(account_id, []) for account_id in account_ids}


class FakePersonRepository:
    def __init__(self, people):
        self._people = people

    def find_by_name(self, query):
        return [p for p in self._people if query.lower() in p.display_name.lower()]


def test_builds_report_for_a_uniquely_matched_person(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    issues = [make_issue("GHI-1672")]
    service = WorkloadReportService(
        issue_repository=FakeIssueRepository({"acc-1": issues}),
        person_repository=FakePersonRepository([alice]),
    )

    report = service.build_report("Alice")

    assert report.person == alice
    assert report.issues == issues


def test_raises_when_no_person_matches():
    service = WorkloadReportService(
        issue_repository=FakeIssueRepository({}),
        person_repository=FakePersonRepository([]),
    )

    with pytest.raises(PersonNotFoundError):
        service.build_report("Nobody")


def test_raises_when_multiple_people_match():
    people = [
        Person(account_id="acc-1", display_name="Alice Wu"),
        Person(account_id="acc-2", display_name="Alice Lin"),
    ]
    service = WorkloadReportService(
        issue_repository=FakeIssueRepository({}),
        person_repository=FakePersonRepository(people),
    )

    with pytest.raises(AmbiguousPersonError):
        service.build_report("Alice")


def test_allocation_by_project_splits_by_percentage(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    issues = [
        make_issue("GHI-1", project_key="GHI"),
        make_issue("GHI-2", project_key="GHI"),
        make_issue("ABC-1", project_key="ABC"),
        make_issue("ABC-2", project_key="ABC"),
    ]
    service = WorkloadReportService(
        issue_repository=FakeIssueRepository({"acc-1": issues}),
        person_repository=FakePersonRepository([alice]),
    )

    report = service.build_report("Alice")

    assert report.allocation_by_project == {"GHI": 50.0, "ABC": 50.0}


def test_build_report_for_person_skips_name_resolution(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    issues = [make_issue("GHI-1672")]
    service = WorkloadReportService(
        issue_repository=FakeIssueRepository({"acc-1": issues}),
        person_repository=FakePersonRepository([]),  # would fail name resolution
    )

    report = service.build_report_for_person(alice)

    assert report.person == alice
    assert report.issues == issues


def test_build_reports_for_people_returns_one_report_per_person(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    amy = Person(account_id="acc-2", display_name="Amy Lin")
    alice_issues = [make_issue("GHI-1")]
    amy_issues = [make_issue("GHI-2"), make_issue("ABC-1", project_key="ABC")]
    service = WorkloadReportService(
        issue_repository=FakeIssueRepository({"acc-1": alice_issues, "acc-2": amy_issues}),
        person_repository=FakePersonRepository([]),  # would fail name resolution
    )

    reports = service.build_reports_for_people([alice, amy])

    assert [r.person for r in reports] == [alice, amy]
    assert reports[0].issues == alice_issues
    assert reports[1].issues == amy_issues


def test_build_reports_for_people_is_empty_for_an_empty_roster():
    service = WorkloadReportService(
        issue_repository=FakeIssueRepository({}),
        person_repository=FakePersonRepository([]),
    )

    assert service.build_reports_for_people([]) == []


def test_active_issues_matches_running_and_reviewing_by_name(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    running = make_issue("GHI-1", status_name="Running / 執行中")
    reviewing = make_issue("GHI-2", status_name="Reviewing / 驗收")
    pending = make_issue("GHI-3", status_name="Pending")
    submitted = make_issue("GHI-4", status_name="Submitted / 提交")
    report = WorkloadReport(person=alice, issues=[running, reviewing, pending, submitted])

    assert set(issue.key for issue in report.active_issues) == {"GHI-1", "GHI-2"}
    assert set(issue.key for issue in report.backlog_issues) == {"GHI-3", "GHI-4"}


def test_active_issues_are_sorted_by_due_date_with_undated_last(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    no_due_date = make_issue("GHI-1", status_name="Running", due_date=None)
    due_later = make_issue("GHI-2", status_name="Running", due_date=date(2026, 12, 1))
    due_sooner = make_issue("GHI-3", status_name="Running", due_date=date(2026, 9, 1))
    report = WorkloadReport(person=alice, issues=[no_due_date, due_later, due_sooner])

    assert [issue.key for issue in report.active_issues] == ["GHI-3", "GHI-2", "GHI-1"]


def test_active_issues_list_reviewing_ones_after_the_running_ones(make_issue):
    """A ticket in review sinks below everything still being worked, even
    when it is due sooner or has no date at all; due date orders each
    group separately.
    """
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    review_due_soon = make_issue("GHI-1", status_name="Reviewing / 驗收", due_date=date(2026, 9, 1))
    run_no_date = make_issue("GHI-2", status_name="Running / 執行中", due_date=None)
    run_due = make_issue("GHI-3", status_name="Running / 執行中", due_date=date(2026, 12, 1))
    review_no_date = make_issue("GHI-4", status_name="Reviewing / 驗收", due_date=None)
    report = WorkloadReport(person=alice, issues=[review_no_date, run_no_date, review_due_soon, run_due])

    assert [issue.key for issue in report.active_issues] == ["GHI-3", "GHI-2", "GHI-1", "GHI-4"]


def test_backlog_issues_excludes_active_ones(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    running = make_issue("GHI-1", status_name="Running")
    pending = make_issue("GHI-2", status_name="Pending")
    report = WorkloadReport(person=alice, issues=[running, pending])

    assert report.backlog_issues == [pending]


def test_allocation_by_project_is_empty_when_no_issues():
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    service = WorkloadReportService(
        issue_repository=FakeIssueRepository({}),
        person_repository=FakePersonRepository([alice]),
    )

    report = service.build_report("Alice")

    assert report.allocation_by_project == {}


def test_the_roster_is_fetched_in_one_batch(make_issue):
    """The per-person loop cost one sequential Jira search per member,
    which dominated the workload and risk pages' load time.
    """
    people = [Person(account_id=f"acc-{index}", display_name=f"Person {index}") for index in range(5)]
    repository = FakeIssueRepository({"acc-0": [make_issue("GHI-1")]})
    service = WorkloadReportService(
        issue_repository=repository,
        person_repository=FakePersonRepository(people),
    )

    reports = service.build_reports_for_people(people)

    assert repository.batch_calls == 1
    assert len(reports) == 5
    assert [report.person for report in reports] == people
    assert [issue.key for issue in reports[0].issues] == ["GHI-1"]
    assert reports[1].issues == []


def test_active_issues_is_computed_once_per_report(make_issue):
    """`backlog_issues` reads `active_issues`, and the workload page's three
    presenters each read both more than once — so this used to re-run the
    filter-and-sort about eight times per member per request.
    """
    report = WorkloadReport(
        person=Person(account_id="acc-1", display_name="Alice Wu"),
        issues=[make_issue("GHI-1", status_name="Running / 執行中", due_date=date(2026, 9, 10))],
    )

    first = report.active_issues
    assert report.active_issues is first, "cached, not recomputed"
    assert report.backlog_issues is report.backlog_issues


@pytest.mark.parametrize(
    "today, expected_monday",
    [
        (date(2026, 9, 7), date(2026, 9, 7)),  # a Monday is its own week start
        (date(2026, 9, 11), date(2026, 9, 7)),  # Friday looks back to Monday
        (date(2026, 9, 13), date(2026, 9, 7)),  # Sunday still belongs to that week
    ],
)
def test_start_of_week_is_the_monday_of_that_week(today, expected_monday):
    assert start_of_week(today) == expected_monday


def test_build_reports_for_people_skips_the_done_query_unless_asked(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    repository = FakeIssueRepository({"acc-1": [make_issue("GHI-1")]})
    service = WorkloadReportService(
        issue_repository=repository,
        person_repository=FakePersonRepository([]),
    )

    [report] = service.build_reports_for_people([alice])

    assert repository.done_queries == []
    assert report.done_issues == []
    assert report.completed_issues == []


def test_build_reports_for_people_attaches_completed_work_when_asked(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    amy = Person(account_id="acc-2", display_name="Amy Lin")
    done = [make_issue("GHI-9", status_name="Done", status_category=StatusCategory.DONE)]
    repository = FakeIssueRepository({"acc-1": [make_issue("GHI-1")]}, done_by_account={"acc-1": done})
    service = WorkloadReportService(
        issue_repository=repository,
        person_repository=FakePersonRepository([]),
    )

    reports = service.build_reports_for_people([alice, amy], completed_since=date(2026, 9, 7))

    assert repository.done_queries == [date(2026, 9, 7)]
    assert reports[0].done_issues == done
    assert reports[1].done_issues == []
    # Finished work stays out of every open-work view.
    assert [issue.key for issue in reports[0].issues] == ["GHI-1"]
    assert [issue.key for issue in reports[0].active_issues] == []
    assert [issue.key for issue in reports[0].backlog_issues] == ["GHI-1"]


def test_completed_issues_are_ordered_newest_first_with_undated_last(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    older = make_issue("GHI-1", completed_at=datetime(2026, 9, 8, 9, 0, tzinfo=timezone.utc))
    newer = make_issue("GHI-2", completed_at=datetime(2026, 9, 10, 17, 3, tzinfo=timezone.utc))
    undated = make_issue("GHI-3", completed_at=None)
    report = WorkloadReport(person=alice, done_issues=[older, undated, newer])

    assert [issue.key for issue in report.completed_issues] == ["GHI-2", "GHI-1", "GHI-3"]
