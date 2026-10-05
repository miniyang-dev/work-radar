"""Unit tests for workload_view's 重要但尚未開票 block.

Uses the real presenters module, which builds issue URLs from the Jira
settings conftest pins for the whole suite — no .env and no network.
"""
from __future__ import annotations

from datetime import datetime, timezone

from work_radar.application.workload_report import WorkloadReport
from work_radar.domain.models import Person, TrackingItem, TrackingStatus
from work_radar.web.presenters import workload_view

NOW = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)
ALICE = Person(account_id="acc-1", display_name="Alice Wu")


def make_item(item_id="id-1", **overrides):
    fields = {"id": item_id, "item": f"item {item_id}", "created_at": NOW, "updated_at": NOW}
    fields.update(overrides)
    return TrackingItem(**fields)


def test_carries_the_unticketed_items_it_is_handed():
    view = workload_view(WorkloadReport(person=ALICE), unticketed=[make_item(item="還沒開票的事")])

    assert view["unticketed_count"] == 1
    assert view["unticketed_items"][0]["item"] == "還沒開票的事"


def test_the_block_is_empty_by_default():
    """Every other caller of workload_view passes nothing, and the template
    hides the block on a zero count.
    """
    view = workload_view(WorkloadReport(person=ALICE))

    assert view["unticketed_count"] == 0
    assert view["unticketed_items"] == []


def test_unticketed_items_keep_their_tracking_fields(make_issue):
    """The block renders tracking rows, not issue rows — status label,
    priority and 追蹤日期 all come from the follow-up list's own vocabulary.
    """
    item = make_item(status=TrackingStatus.WAITING, item="等 Carol 回覆授權")
    report = WorkloadReport(person=ALICE, issues=[make_issue("GHI-1", status_name="Running")])

    (row,) = workload_view(report, unticketed=[item])["unticketed_items"]

    assert row["status_label"] == "等待回覆"
    assert row["priority_label"] == "中"
    assert row["due_date"] == ""
    # And it does not disturb the issue-derived halves of the view.
    assert [issue["key"] for issue in workload_view(report)["active_issues"]] == ["GHI-1"]


def test_a_reviewing_ticket_gets_its_own_status_colour_apart_from_running(make_issue):
    from work_radar.domain.models import StatusCategory
    from work_radar.web.presenters import issue_row

    running = make_issue("GHI-1", status_name="Running / 執行中", status_category=StatusCategory.IN_PROGRESS)
    reviewing = make_issue("GHI-2", status_name="Reviewing / 驗收", status_category=StatusCategory.IN_PROGRESS)

    assert issue_row(running)["status_css"] == "status-progress"
    assert issue_row(reviewing)["status_css"] == "status-review"
