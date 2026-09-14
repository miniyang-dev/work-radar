"""Core domain entities and value objects.

Nothing in this module knows about Jira, HTTP, or any other infrastructure
detail — it describes the problem domain only, so it has no dependencies
and needs no mocking to test.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


class StatusCategory(str, Enum):
    """A tracker-agnostic bucket for whatever granular status a tool uses."""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


@dataclass(frozen=True)
class Status:
    name: str
    category: StatusCategory


@dataclass(frozen=True)
class Person:
    account_id: str
    display_name: str
    email: str | None = None


@dataclass(frozen=True)
class Issue:
    key: str
    summary: str
    status: Status
    project_key: str
    issue_type: str
    updated_at: datetime
    created_at: datetime
    assignee: Person | None = None
    priority: str | None = None
    parent_key: str | None = None
    parent_summary: str | None = None
    start_date: date | None = None
    due_date: date | None = None
    # When the issue entered the Done category; None while it is still
    # open. Not the same as `updated_at`, which keeps moving every time
    # someone comments on a finished ticket.
    completed_at: datetime | None = None

    @property
    def is_open(self) -> bool:
        return self.status.category != StatusCategory.DONE

    @property
    def is_unassigned(self) -> bool:
        return self.assignee is None


@dataclass(frozen=True)
class Comment:
    author: str
    body: str
    created_at: datetime


@dataclass(frozen=True)
class StatusTransition:
    """One status change from an issue's changelog.

    `from_status`/`to_status` are status *names* (e.g. "Running / 執行中"),
    not categories — Jira's changelog doesn't carry the category, only the
    display string. Classifying a transition requires a name->category
    lookup built separately (see application/cycle_time.py).
    """

    from_status: str | None
    to_status: str
    occurred_at: datetime


class TrackingStatus(str, Enum):
    """The follow-up list's own fixed vocabulary.

    Deliberately separate from StatusCategory: that one buckets whatever
    granular status a tracker reports, while this is a hand-kept set that
    includes two states no Jira workflow here models — waiting on someone
    else to come back, and parked on purpose.
    """

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    WAITING = "waiting"
    DONE = "done"
    ON_HOLD = "on_hold"


class TrackingPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class TrackingNote:
    """One 備註 entry, stamped with when it was written.

    Notes accumulate instead of overwriting: chasing something is a
    running record ("問了", "還在等", "已回覆"), and the useful part is
    usually *when* each line was added — which is why the timestamp sits
    on the note rather than being read off the item's updated_at.
    """

    text: str
    created_at: datetime


@dataclass(frozen=True)
class TrackingItem:
    """One thing someone decided to follow up on, typed in by hand.

    Not an Issue: no tracker stands behind it, so the id is work-radar's
    own and nothing here can be re-fetched or reconciled against Jira.
    """

    id: str
    item: str
    created_at: datetime
    updated_at: datetime
    status: TrackingStatus = TrackingStatus.TODO
    priority: TrackingPriority = TrackingPriority.MEDIUM
    due_date: date | None = None
    owner: str | None = None
    # A roster member's account id, set when this item should also surface
    # on that person's workload page. Deliberately not `owner`: that one is
    # free text (often someone outside the team, or a whole department),
    # while this has to match a Person exactly to route the item anywhere.
    member_account_id: str | None = None
    link: str | None = None
    # Oldest first, so the field reads as the history it is. A tuple, not
    # a list, keeps the frozen dataclass genuinely immutable: appending is
    # rebuilding the item, which is exactly what advances updated_at.
    notes: tuple[TrackingNote, ...] = ()

    @property
    def is_active(self) -> bool:
        """Still needs chasing — 已完成 and 已擱置 both drop out of the
        follow-up list, for different reasons.
        """
        return self.status not in (TrackingStatus.DONE, TrackingStatus.ON_HOLD)
