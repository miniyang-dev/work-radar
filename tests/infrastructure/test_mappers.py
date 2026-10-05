"""Unit tests for Jira JSON -> domain model mapping. No network involved."""
from __future__ import annotations

from datetime import date

import pytest

from work_radar.domain.models import StatusCategory
from work_radar.infrastructure.jira.mappers import (
    START_DATE_FIELD,
    STATUS_CATEGORY_CHANGED_FIELD,
    _parse_timestamp,
    adf_to_plain_text,
    to_comment,
    to_issue,
    to_person,
    to_status,
    to_transitions,
)


def test_to_status_maps_known_categories():
    assert to_status({"name": "Done", "statusCategory": {"key": "done"}}).category == StatusCategory.DONE
    assert (
        to_status({"name": "Running", "statusCategory": {"key": "indeterminate"}}).category
        == StatusCategory.IN_PROGRESS
    )


def test_to_status_defaults_unknown_category_to_todo():
    status = to_status({"name": "Weird", "statusCategory": {"key": "something-new"}})
    assert status.category == StatusCategory.TODO


def test_to_person_falls_back_to_account_id_when_display_name_missing():
    person = to_person({"accountId": "abc123"})
    assert person.display_name == "abc123"
    assert person.email is None


def test_to_issue_parses_timestamp_with_offset_and_no_colon():
    raw = {
        "key": "GHI-1545",
        "fields": {
            "summary": "Threads 渠道 Pipeline 重構",
            "status": {"name": "Running", "statusCategory": {"key": "indeterminate"}},
            "project": {"key": "GHI"},
            "issuetype": {"name": "Epic"},
            "updated": "2026-09-04T16:37:10.968+0800",
            "created": "2026-01-01T09:00:00.000+0800",
            "duedate": "2026-09-25",
            START_DATE_FIELD: "2026-09-18",
            "assignee": {"accountId": "acc-1", "displayName": "Alice Wu"},
            "priority": {"name": "Medium"},
        },
    }

    issue = to_issue(raw)

    assert issue.key == "GHI-1545"
    assert issue.assignee is not None
    assert issue.assignee.display_name == "Alice Wu"
    assert issue.priority == "Medium"
    assert issue.updated_at.utcoffset().total_seconds() == 8 * 3600
    assert issue.created_at.year == 2026 and issue.created_at.month == 1
    assert issue.start_date == date(2026, 9, 18)
    assert issue.due_date == date(2026, 9, 25)


def test_to_issue_handles_missing_optional_fields():
    raw = {
        "key": "GHI-1637",
        "fields": {
            "summary": "Production 資源建立",
            "status": {"name": "Submitted", "statusCategory": {"key": "new"}},
            "project": {"key": "GHI"},
            "issuetype": {"name": "Task"},
            "updated": "2026-05-25T11:31:13.239+0800",
            "created": "2026-05-01T09:00:00.000+0800",
        },
    }

    issue = to_issue(raw)

    assert issue.assignee is None
    assert issue.priority is None
    assert issue.parent_key is None
    assert issue.is_unassigned is True
    assert issue.start_date is None
    assert issue.due_date is None


def test_to_issue_reads_completed_at_from_the_status_category_change():
    raw = {
        "key": "ABC-1583",
        "fields": {
            "summary": "熱門文章重複顯示",
            "status": {"name": "Done", "statusCategory": {"key": "done"}},
            "project": {"key": "ABC"},
            "issuetype": {"name": "Task"},
            "updated": "2026-09-11T09:00:00.000+0800",
            "created": "2026-09-01T09:00:00.000+0800",
            STATUS_CATEGORY_CHANGED_FIELD: "2026-09-10T17:03:25.671+0800",
        },
    }

    issue = to_issue(raw)

    assert issue.completed_at is not None
    assert issue.completed_at.strftime("%Y-%m-%d %H:%M") == "2026-09-10 17:03"


def test_to_issue_ignores_the_status_category_change_on_an_open_issue():
    """Jira stamps that field on any category change, so on an in-progress
    issue it marks when work *started* — reading it as a completion time
    would report every running ticket as finished.
    """
    raw = {
        "key": "ABC-1581",
        "fields": {
            "summary": "IG 帳號資料 dehub 回補失敗排查",
            "status": {"name": "Running / 執行中", "statusCategory": {"key": "indeterminate"}},
            "project": {"key": "ABC"},
            "issuetype": {"name": "Task"},
            "updated": "2026-09-11T09:05:00.000+0800",
            "created": "2026-09-01T09:00:00.000+0800",
            STATUS_CATEGORY_CHANGED_FIELD: "2026-09-02T10:00:00.000+0800",
        },
    }

    assert to_issue(raw).completed_at is None


def test_adf_to_plain_text_joins_paragraphs_with_newlines():
    document = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "First line."}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "Second line."}]},
        ],
    }

    assert adf_to_plain_text(document) == "First line.\nSecond line."


def test_adf_to_plain_text_handles_mentions_and_hard_breaks():
    document = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "mention", "attrs": {"id": "acc-1", "text": "@Alice"}},
                    {"type": "text", "text": " please check"},
                    {"type": "hardBreak"},
                    {"type": "text", "text": "this."},
                ],
            }
        ],
    }

    assert adf_to_plain_text(document) == "@Alice please check\nthis."


def test_adf_to_plain_text_returns_empty_string_for_missing_body():
    assert adf_to_plain_text(None) == ""


def test_to_comment_parses_author_body_and_timestamp():
    raw = {
        "author": {"accountId": "acc-1", "displayName": "Alice Wu"},
        "body": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "LGTM"}]}]},
        "created": "2026-09-07T10:56:14.787+0800",
    }

    comment = to_comment(raw)

    assert comment.author == "Alice Wu"
    assert comment.body == "LGTM"
    assert comment.created_at.year == 2026 and comment.created_at.month == 9


def test_to_transitions_extracts_only_status_field_changes():
    histories = [
        {
            "created": "2026-09-07T10:56:14.787+0800",
            "items": [
                {"field": "status", "fromString": "Running / 執行中", "toString": "Done"},
                {"field": "assignee", "fromString": "A", "toString": "B"},
            ],
        },
        {
            "created": "2026-01-19T14:21:44.564+0800",
            "items": [{"field": "status", "fromString": "Submitted", "toString": "Approved"}],
        },
    ]

    transitions = to_transitions(histories)

    assert len(transitions) == 2
    assert transitions[0].from_status == "Running / 執行中"
    assert transitions[0].to_status == "Done"
    assert transitions[1].to_status == "Approved"


def test_parses_timestamps_with_and_without_milliseconds():
    """Milliseconds are usual but not guaranteed; a strict `.%f` format
    turned a single millisecond-less timestamp into a page-wide crash.
    """
    with_ms = _parse_timestamp("2026-09-04T16:37:10.968+0800")
    without_ms = _parse_timestamp("2026-09-04T16:37:10+0800")

    assert with_ms.microsecond == 968000
    assert without_ms.microsecond == 0
    assert without_ms.replace(microsecond=968000) == with_ms


def test_unrecognized_timestamp_raises_a_readable_error():
    with pytest.raises(ValueError, match="Unrecognized Jira timestamp"):
        _parse_timestamp("last Tuesday")


def test_to_issue_reads_labels():
    raw = {
        "key": "GHI-1684",
        "fields": {
            "summary": "Gemini 遷移",
            "status": {"name": "Running", "statusCategory": {"key": "indeterminate"}},
            "project": {"key": "GHI"},
            "issuetype": {"name": "Task"},
            "updated": "2026-09-30T13:56:00.000+0800",
            "created": "2026-09-01T09:00:00.000+0800",
            "labels": ["內部任務", "cost"],
        },
    }

    assert to_issue(raw).labels == ("內部任務", "cost")


def test_to_issue_has_no_labels_when_the_field_is_missing_or_null():
    base = {
        "summary": "x",
        "status": {"name": "Running", "statusCategory": {"key": "indeterminate"}},
        "project": {"key": "GHI"},
        "issuetype": {"name": "Task"},
        "updated": "2026-09-30T13:56:00.000+0800",
        "created": "2026-09-01T09:00:00.000+0800",
    }

    assert to_issue({"key": "GHI-1", "fields": base}).labels == ()
    assert to_issue({"key": "GHI-2", "fields": {**base, "labels": None}}).labels == ()
