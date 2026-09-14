"""Infrastructure-level error for the Jira adapter.

Deliberately not a WorkRadarError subclass: the domain layer shouldn't
know that "Jira" or "HTTP status codes" exist. Repositories translate this
into a domain exception where one applies (e.g. 404 -> IssueNotFoundError);
the composition root catches whatever is left.
"""
from __future__ import annotations


class JiraApiError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"Jira API error {status_code}: {message}")
        self.status_code = status_code
