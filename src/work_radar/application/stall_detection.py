"""Use case: detect open issues that haven't been updated in a while.

Pure domain policy — takes a list of Issue and a reference time, returns a
list of Issue. No I/O, so it needs no mocking to unit test, and it has no
reason to change if the data source ever changes (Open/Closed: a different
stall policy is a different class implementing the same shape, not an edit
to this one).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from work_radar.domain.models import Issue

DEFAULT_STALL_THRESHOLD_DAYS = 14


@dataclass(frozen=True)
class StaleIssueFinder:
    threshold_days: int = DEFAULT_STALL_THRESHOLD_DAYS

    def find_stale(self, issues: list[Issue], as_of: datetime) -> list[Issue]:
        cutoff = as_of - timedelta(days=self.threshold_days)
        return [issue for issue in issues if issue.is_open and issue.updated_at < cutoff]
