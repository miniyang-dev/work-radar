"""Domain-level errors.

Kept free of any infrastructure detail (no requests, no Jira-specific
status codes) so they can be raised and caught by application code without
importing anything about how data is actually fetched.
"""
from __future__ import annotations

from work_radar.domain.models import Person


class WorkRadarError(Exception):
    """Base class for all work-radar domain errors."""


class IssueNotFoundError(WorkRadarError):
    def __init__(self, key: str) -> None:
        super().__init__(f"Issue '{key}' was not found.")
        self.key = key


class PersonNotFoundError(WorkRadarError):
    def __init__(self, query: str) -> None:
        super().__init__(f"No person matching '{query}' was found.")
        self.query = query


class AmbiguousPersonError(WorkRadarError):
    def __init__(self, query: str, matches: list[Person]) -> None:
        names = ", ".join(f"{m.display_name} <{m.email or 'no email'}>" for m in matches)
        super().__init__(f"'{query}' matched multiple people: {names}")
        self.query = query
        self.matches = matches
