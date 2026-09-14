"""Unit tests for IssueCommentService using an in-memory fake IssueCommentRepository."""
from __future__ import annotations

from datetime import datetime, timezone

from work_radar.application.issue_comments import IssueCommentService
from work_radar.domain.models import Comment


class FakeIssueCommentRepository:
    def __init__(self, comments_by_key: dict) -> None:
        self._comments_by_key = comments_by_key

    def get_comments(self, key):
        return self._comments_by_key.get(key, [])


def test_list_comments_returns_newest_first():
    older = Comment(author="Alice", body="first", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    newer = Comment(author="Amy", body="second", created_at=datetime(2026, 6, 1, tzinfo=timezone.utc))
    service = IssueCommentService(FakeIssueCommentRepository({"GHI-1": [older, newer]}))

    comments = service.list_comments("GHI-1")

    assert comments == [newer, older]


def test_list_comments_is_empty_when_issue_has_none():
    service = IssueCommentService(FakeIssueCommentRepository({}))

    assert service.list_comments("GHI-1") == []
