"""Use case: fetch an issue's comments, newest first.

Newest-first (rather than chronological) since this is meant for a quick
"what's the latest word on this ticket" glance, not for reading a
conversation start to finish.
"""
from __future__ import annotations

from work_radar.domain.models import Comment
from work_radar.domain.ports import IssueCommentRepository


class IssueCommentService:
    def __init__(self, comment_repository: IssueCommentRepository) -> None:
        self._comments = comment_repository

    def list_comments(self, issue_key: str) -> list[Comment]:
        comments = self._comments.get_comments(issue_key)
        return sorted(comments, key=lambda comment: comment.created_at, reverse=True)
