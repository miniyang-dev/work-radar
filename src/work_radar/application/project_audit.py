"""Use case: audit everything a project took in over a window.

Different question from risk_scan.py, which asks "what's wrong with these
*people's* tickets". This one is scoped to *projects* and to an intake
window: what came in, what's still open, how urgent it really is, and
which tickets are missing the fields that make them manageable at all.

The urgency score exists because the obvious answer — sort by Jira's
priority field — doesn't work on a real project: where nearly every
ticket carries the same middle priority, sorting by it produces a flat
list. Being
overdue, sitting untouched for weeks, or having nobody assigned are all
better urgency signals than a field almost nobody sets, and the score
folds all four together with priority still weighing heavily.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from work_radar.application.risk_scan import find_unassigned
from work_radar.application.stall_detection import DEFAULT_STALL_THRESHOLD_DAYS, StaleIssueFinder
from work_radar.domain.models import Issue
from work_radar.domain.ports import IssueRepository

# Two priority schemes coexist on this Jira instance: the P0..P3 one the
# tracked projects actually use, and the stock Highest..Lowest one. Both
# are mapped so the score doesn't silently flatten on a project using the
# other. Anything unrecognised scores as the middle of the range rather
# than as harmless.
_PRIORITY_WEIGHT = {
    "P0": 30,
    "P1": 20,
    "P2": 8,
    "P3": 2,
    "Highest": 30,
    "High": 20,
    "Medium": 8,
    "Low": 2,
    "Lowest": 0,
}
_UNKNOWN_PRIORITY_WEIGHT = 8

# Weights, all tunable in one place. Overdue outranks everything: a base
# of 40 puts any overdue ticket above a fresh P0, and the per-day term
# orders overdue tickets among themselves (capped so a ticket forgotten
# for two years doesn't drown out ten merely-late ones).
_OVERDUE_BASE = 40
_MAX_OVERDUE_DAYS_COUNTED = 30
_MAX_STALE_DAYS_COUNTED = 60
_UNASSIGNED_WEIGHT = 10

# Calibrated against what each signal alone should read as, not picked
# round: any overdue ticket (>=41) must land in 危急, a fresh P0 (30) in
# 高, a fresh P1 (20) or an untouched-for-three-weeks P2 (8+10) in 中.
# Below that is the quiet majority, which on a real backlog is most of
# the queue — saying so plainly is the point.
_URGENCY_THRESHOLDS = ((40, "危急"), (25, "高"), (13, "中"))
_LOWEST_URGENCY_LABEL = "低"


def priority_weight(priority: Optional[str]) -> int:
    return _PRIORITY_WEIGHT.get(priority or "", _UNKNOWN_PRIORITY_WEIGHT)


def urgency_level(score: int) -> str:
    for threshold, label in _URGENCY_THRESHOLDS:
        if score >= threshold:
            return label
    return _LOWEST_URGENCY_LABEL


@dataclass(frozen=True)
class AuditEntry:
    """One issue plus the urgency verdict on it.

    `reasons` carries the same information the score does, in words —
    a bare number nobody can audit is worse than no number at all, so
    every row can show why it ranked where it did.
    """

    issue: Issue
    score: int
    level: str
    reasons: list[str] = field(default_factory=list)
    stale_days: int = 0
    overdue_days: int = 0


@dataclass(frozen=True)
class AuditGaps:
    """Open issues missing the fields that make them trackable.

    Not "risks" in the risk_scan sense — a ticket with no due date isn't
    late, it's unmanageable, which is the thing an audit is for.

    These lists are counted, not listed, by the web page: on a backlog
    where due dates are rarely set, nearly every open issue lands in at
    least one of them, so rendering them as their own tables printed the
    ranked list a second time and said nothing new. The counts still belong on the page; the rows already
    have a home in the ranked list, where being unassigned or stale is
    written out next to the urgency score that used it.
    """

    no_due_date: list[Issue] = field(default_factory=list)
    unassigned: list[Issue] = field(default_factory=list)
    stale: list[Issue] = field(default_factory=list)
    stale_days: int = DEFAULT_STALL_THRESHOLD_DAYS


@dataclass(frozen=True)
class AuditStats:
    total: int = 0
    open_count: int = 0
    done_count: int = 0
    done_rate: int = 0
    overdue_count: int = 0
    high_priority_count: int = 0
    unassigned_count: int = 0
    no_due_date_count: int = 0
    stale_count: int = 0
    median_stale_days: int = 0


@dataclass(frozen=True)
class ProjectAuditReport:
    project_keys: list[str]
    window_days: int
    open_entries: list[AuditEntry] = field(default_factory=list)
    done_issues: list[Issue] = field(default_factory=list)
    gaps: AuditGaps = field(default_factory=AuditGaps)
    stats: AuditStats = field(default_factory=AuditStats)


def score_issue(issue: Issue, as_of: datetime) -> AuditEntry:
    """Scores one open issue. A closed issue always scores 0.

    Nothing about a finished ticket is urgent, and giving closed rows a
    real score would let a long-overdue-but-delivered ticket outrank
    something still burning.
    """
    stale_days = max((as_of - issue.updated_at).days, 0)
    overdue_days = 0
    if issue.due_date is not None and issue.due_date < as_of.date():
        overdue_days = (as_of.date() - issue.due_date).days

    if not issue.is_open:
        return AuditEntry(
            issue=issue,
            score=0,
            level=_LOWEST_URGENCY_LABEL,
            reasons=["已完成"],
            stale_days=stale_days,
            overdue_days=overdue_days,
        )

    score = 0
    reasons: list[str] = []

    if overdue_days:
        score += _OVERDUE_BASE + min(overdue_days, _MAX_OVERDUE_DAYS_COUNTED)
        reasons.append(f"逾期 {overdue_days} 天")

    weight = priority_weight(issue.priority)
    score += weight
    if issue.priority and weight > _PRIORITY_WEIGHT["P2"]:
        reasons.append(issue.priority)

    stale_points = min(stale_days, _MAX_STALE_DAYS_COUNTED) // 2
    if stale_points:
        score += stale_points
        reasons.append(f"{stale_days} 天未更新")

    if issue.is_unassigned:
        score += _UNASSIGNED_WEIGHT
        reasons.append("無人認領")

    return AuditEntry(
        issue=issue,
        score=score,
        level=urgency_level(score),
        reasons=reasons,
        stale_days=stale_days,
        overdue_days=overdue_days,
    )


def _find_without_due_date(issues: list[Issue]) -> list[Issue]:
    return [issue for issue in issues if issue.is_open and issue.due_date is None]


def _build_stats(
    issues: list[Issue], open_entries: list[AuditEntry], gaps: AuditGaps
) -> AuditStats:
    total = len(issues)
    open_count = len(open_entries)
    done_count = total - open_count
    stale_days = [entry.stale_days for entry in open_entries]

    return AuditStats(
        total=total,
        open_count=open_count,
        done_count=done_count,
        done_rate=round(done_count / total * 100) if total else 0,
        overdue_count=sum(1 for entry in open_entries if entry.overdue_days),
        high_priority_count=sum(
            1
            for entry in open_entries
            if priority_weight(entry.issue.priority) > _PRIORITY_WEIGHT["P2"]
        ),
        unassigned_count=len(gaps.unassigned),
        no_due_date_count=len(gaps.no_due_date),
        stale_count=len(gaps.stale),
        median_stale_days=int(statistics.median(stale_days)) if stale_days else 0,
    )


class ProjectAuditService:
    """Fetches a window of a project's intake and ranks it by urgency."""

    def __init__(self, issue_repository: IssueRepository) -> None:
        self._issues = issue_repository

    def build_report(
        self,
        project_keys: list[str],
        *,
        window_days: int,
        as_of: datetime,
        stale_days: int = DEFAULT_STALL_THRESHOLD_DAYS,
    ) -> ProjectAuditReport:
        issues = self._issues.find_issues_created_since_for_projects(project_keys, window_days)

        open_issues = [issue for issue in issues if issue.is_open]
        done_issues = [issue for issue in issues if not issue.is_open]

        # Ties broken by issue key so the order is stable across renders —
        # most of a window scores identically (a fresh, unremarkable P2),
        # and a list that reshuffles on every refresh is unreadable.
        entries = sorted(
            (score_issue(issue, as_of) for issue in open_issues),
            key=lambda entry: (-entry.score, entry.issue.key),
        )

        gaps = AuditGaps(
            no_due_date=_find_without_due_date(open_issues),
            unassigned=find_unassigned(open_issues),
            stale=StaleIssueFinder(threshold_days=stale_days).find_stale(open_issues, as_of),
            stale_days=stale_days,
        )

        return ProjectAuditReport(
            project_keys=list(project_keys),
            window_days=window_days,
            open_entries=entries,
            done_issues=sorted(done_issues, key=lambda issue: issue.updated_at, reverse=True),
            gaps=gaps,
            stats=_build_stats(issues, entries, gaps),
        )
