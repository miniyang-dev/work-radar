"""Unit tests for WeeklyReportService using in-memory fakes for every port."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from work_radar.application.weekly_report import WeeklyReportService
from work_radar.domain.models import Person, StatusCategory, StatusTransition

AS_OF = datetime(2026, 9, 7, tzinfo=timezone.utc)
WINDOW_DAYS = 7


class FakeIssueRepository:
    def __init__(self, touched_issues, open_issues):
        self._touched_issues = touched_issues
        self._open_issues = open_issues

    def get_issue(self, key):
        raise NotImplementedError

    def find_children(self, parent_key):
        raise NotImplementedError

    def find_open_issues_for_assignee(self, account_id):
        return self._open_issues

    def find_open_issues_for_projects(self, project_keys):
        raise NotImplementedError

    def find_done_issues_for_projects(self, project_keys, window_days):
        raise NotImplementedError

    def find_issues_updated_since_for_assignee(self, account_id, window_days):
        return self._touched_issues


class FakePersonRepository:
    def __init__(self, people):
        self._people = people

    def find_by_name(self, query):
        return [p for p in self._people if query.lower() in p.display_name.lower()]


class FakeHistoryRepository:
    def __init__(self, transitions_by_key):
        self._transitions_by_key = transitions_by_key
        self.batch_calls = 0

    def get_transitions(self, key):
        return self._transitions_by_key.get(key, [])

    def get_transitions_for_issues(self, keys):
        self.batch_calls += 1
        return {key: self._transitions_by_key.get(key, []) for key in keys}


class FakeStatusCatalogRepository:
    def __init__(self, catalogs_by_project):
        self._catalogs_by_project = catalogs_by_project

    def get_status_catalog(self, project_key):
        return self._catalogs_by_project.get(project_key, {})


def test_classifies_completed_in_progress_and_stuck(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")

    completed_issue = make_issue("GHI-1", status_name="Done", status_category=StatusCategory.DONE)
    moved_issue = make_issue("GHI-2", status_name="Running", status_category=StatusCategory.IN_PROGRESS)
    untouched_open_issue = make_issue(
        "GHI-3",
        status_category=StatusCategory.IN_PROGRESS,
        updated_at=AS_OF - timedelta(days=40),
    )

    service = WeeklyReportService(
        issue_repository=FakeIssueRepository(
            touched_issues=[completed_issue, moved_issue],
            open_issues=[untouched_open_issue],
        ),
        person_repository=FakePersonRepository([alice]),
        history_repository=FakeHistoryRepository(
            {
                "GHI-1": [
                    StatusTransition(from_status="Running", to_status="Done", occurred_at=AS_OF - timedelta(days=1))
                ],
                "GHI-2": [
                    StatusTransition(
                        from_status="Submitted", to_status="Running", occurred_at=AS_OF - timedelta(days=2)
                    )
                ],
            }
        ),
        status_catalog_repository=FakeStatusCatalogRepository(
            {"GHI": {"Submitted": StatusCategory.TODO, "Running": StatusCategory.IN_PROGRESS, "Done": StatusCategory.DONE}}
        ),
    )

    report = service.build_report("Alice", as_of=AS_OF, window_days=WINDOW_DAYS)

    assert report.completed == [completed_issue]
    assert report.in_progress == [moved_issue]
    assert report.stuck == [untouched_open_issue]


def test_build_report_for_person_skips_name_resolution(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    completed_issue = make_issue("GHI-1", status_name="Done", status_category=StatusCategory.DONE)

    service = WeeklyReportService(
        issue_repository=FakeIssueRepository(touched_issues=[completed_issue], open_issues=[]),
        person_repository=FakePersonRepository([]),  # would fail name resolution
        history_repository=FakeHistoryRepository(
            {"GHI-1": [StatusTransition(from_status="Running", to_status="Done", occurred_at=AS_OF - timedelta(days=1))]}
        ),
        status_catalog_repository=FakeStatusCatalogRepository(
            {"GHI": {"Running": StatusCategory.IN_PROGRESS, "Done": StatusCategory.DONE}}
        ),
    )

    report = service.build_report_for_person(alice, as_of=AS_OF, window_days=WINDOW_DAYS)

    assert report.person == alice
    assert report.completed == [completed_issue]


def test_transitions_before_the_window_do_not_count_as_completed(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    old_transition_issue = make_issue("GHI-1", status_name="Done", status_category=StatusCategory.DONE)

    service = WeeklyReportService(
        issue_repository=FakeIssueRepository(touched_issues=[old_transition_issue], open_issues=[]),
        person_repository=FakePersonRepository([alice]),
        history_repository=FakeHistoryRepository(
            {
                "GHI-1": [
                    StatusTransition(
                        from_status="Running", to_status="Done", occurred_at=AS_OF - timedelta(days=30)
                    )
                ]
            }
        ),
        status_catalog_repository=FakeStatusCatalogRepository(
            {"GHI": {"Running": StatusCategory.IN_PROGRESS, "Done": StatusCategory.DONE}}
        ),
    )

    report = service.build_report("Alice", as_of=AS_OF, window_days=WINDOW_DAYS)

    assert report.completed == []
    assert report.in_progress == []


def test_an_issue_touched_without_a_status_change_is_still_reported(make_issue):
    """Commenting on a ticket, reassigning it, or moving its due date all
    count as touching it. Those issues used to fall out of the report
    entirely — neither completed, in progress, nor stuck — which
    contradicts "what did you touch but not finish".
    """
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    commented_only = make_issue("GHI-9", status_name="Running", status_category=StatusCategory.IN_PROGRESS)

    service = WeeklyReportService(
        issue_repository=FakeIssueRepository(touched_issues=[commented_only], open_issues=[]),
        person_repository=FakePersonRepository([alice]),
        history_repository=FakeHistoryRepository({}),  # no status history at all
        status_catalog_repository=FakeStatusCatalogRepository(
            {"GHI": {"Running": StatusCategory.IN_PROGRESS, "Done": StatusCategory.DONE}}
        ),
    )

    report = service.build_report("Alice", as_of=AS_OF, window_days=WINDOW_DAYS)

    assert report.in_progress == [commented_only]
    assert report.completed == []


def test_an_already_done_issue_with_a_late_comment_stays_out_of_both_buckets(make_issue):
    """It wasn't completed in this window and isn't in progress either."""
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    long_done = make_issue("GHI-8", status_name="Done", status_category=StatusCategory.DONE)

    service = WeeklyReportService(
        issue_repository=FakeIssueRepository(touched_issues=[long_done], open_issues=[]),
        person_repository=FakePersonRepository([alice]),
        history_repository=FakeHistoryRepository({}),
        status_catalog_repository=FakeStatusCatalogRepository({"GHI": {"Done": StatusCategory.DONE}}),
    )

    report = service.build_report("Alice", as_of=AS_OF, window_days=WINDOW_DAYS)

    assert report.completed == []
    assert report.in_progress == []


def test_changelogs_are_fetched_in_one_batch(make_issue):
    """One request for the whole window, not one per touched issue."""
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    touched = [make_issue(f"DE-{index}", status_category=StatusCategory.IN_PROGRESS) for index in range(5)]
    history = FakeHistoryRepository({})

    service = WeeklyReportService(
        issue_repository=FakeIssueRepository(touched_issues=touched, open_issues=[]),
        person_repository=FakePersonRepository([alice]),
        history_repository=history,
        status_catalog_repository=FakeStatusCatalogRepository({"GHI": {}}),
    )

    service.build_report("Alice", as_of=AS_OF, window_days=WINDOW_DAYS)

    assert history.batch_calls == 1
