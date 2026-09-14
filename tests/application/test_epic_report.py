"""Unit tests for EpicReportService using an in-memory fake IssueRepository."""
from __future__ import annotations

from work_radar.application.epic_report import EpicReportService
from work_radar.domain.models import StatusCategory


class FakeIssueRepository:
    def __init__(self, epic, children):
        self._epic = epic
        self._children = children

    def get_issue(self, key):
        assert key == self._epic.key
        return self._epic

    def find_children(self, parent_key):
        return self._children

    def find_open_issues_for_assignee(self, account_id):
        raise NotImplementedError("not needed for these tests")


def test_report_summarizes_child_status_counts(make_issue):
    epic = make_issue("GHI-1545", status_category=StatusCategory.IN_PROGRESS)
    done_child = make_issue("GHI-1591", status_name="Done", status_category=StatusCategory.DONE)
    running_child = make_issue("GHI-1646", status_name="Running", status_category=StatusCategory.IN_PROGRESS)
    repository = FakeIssueRepository(epic, [done_child, running_child])
    service = EpicReportService(repository)

    report = service.build_report("GHI-1545")

    assert report.epic == epic
    assert report.children == [done_child, running_child]
    assert report.status_counts == {"Done": 1, "Running": 1}


def test_open_children_excludes_done_issues(make_issue):
    epic = make_issue("GHI-1545")
    done_child = make_issue("GHI-1591", status_name="Done", status_category=StatusCategory.DONE)
    open_child = make_issue("GHI-1646", status_category=StatusCategory.IN_PROGRESS)
    repository = FakeIssueRepository(epic, [done_child, open_child])
    service = EpicReportService(repository)

    report = service.build_report("GHI-1545")

    assert report.open_children == [open_child]
