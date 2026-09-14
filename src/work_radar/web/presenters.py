"""HTML-oriented view models.

Plays the same role for the web adapter that cli/presenters.py plays for
the CLI: turns application-layer reports into plain dicts a template can
render. Templates never touch an Issue/EpicReport object directly, so the
application layer stays free to change shape without breaking a template.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from functools import lru_cache
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from work_radar.application.epic_report import EpicReport
from work_radar.application.project_audit import AuditEntry, ProjectAuditReport
from work_radar.application.risk_scan import TeamRiskReport
from work_radar.application.weekly_report import WeeklyReport
from work_radar.application.workload_report import WorkloadReport
from work_radar.domain.models import (
    Comment,
    Issue,
    Person,
    StatusCategory,
    TrackingItem,
    TrackingPriority,
    TrackingStatus,
)
from work_radar.infrastructure.config import JiraConfig, overview_project_rank_from_env


@lru_cache(maxsize=1)
def _jira_domain() -> str:
    return JiraConfig.from_env().domain


def _issue_url(key: str) -> str:
    """The human-facing Jira page for an issue — not the api.atlassian.com
    gateway URL used for actual API calls, so it opens in a normal
    logged-in browser tab.
    """
    return f"https://{_jira_domain()}/browse/{key}"

_STATUS_CSS_CLASS = {
    StatusCategory.DONE: "status-done",
    StatusCategory.IN_PROGRESS: "status-progress",
    StatusCategory.TODO: "status-todo",
}

# A monday.com-style board gives every person a stable colored avatar.
# Plain string hashing isn't deterministic across process restarts
# (PYTHONHASHSEED), so the palette index is derived from character codes
# instead — same name always lands on the same color.
_AVATAR_PALETTE = [
    "#579bfc",  # blue
    "#a25ddc",  # purple
    "#037f4c",  # dark green
    "#fdab3d",  # orange
    "#e2445c",  # red
    "#00c875",  # green
    "#ff642e",  # deep orange
    "#66ccff",  # light blue
    "#9d99b9",  # muted purple
    "#cab641",  # olive
]


def _avatar(display_name: str) -> Dict[str, str]:
    words = display_name.split()
    initials = "".join(word[0] for word in words[:2]).upper() or "?"
    color = _AVATAR_PALETTE[sum(ord(char) for char in display_name) % len(_AVATAR_PALETTE)]
    return {"initials": initials, "color": color}


# The two halves of flagging a dated row: the date itself, and the row it
# sits in. Same state drives both, so they can never disagree.
_DUE_DATE_TEXT_CSS = {"overdue": "overdue-text", "scheduled": "scheduled-text"}
_DUE_DATE_ROW_CSS = {"overdue": "row-overdue", "scheduled": "row-scheduled"}


def _due_state(due_date: Optional[date]) -> str:
    """How a due date should read when the table is asked to flag them.

    Three states rather than two: a date that has passed is the red the
    whole app already reads as "逾期", while a date still ahead gets the
    in-progress amber. The distinction matters most in the backlog, where
    a dated ticket is scheduled work nobody has started — and a red one
    there is already late without ever having been picked up.
    """
    if due_date is None:
        return ""
    return "overdue" if due_date < date.today() else "scheduled"


def issue_row(issue: Issue) -> Dict[str, Any]:
    assignee_name = issue.assignee.display_name if issue.assignee else None
    due_state = _due_state(issue.due_date)
    return {
        "key": issue.key,
        "url": _issue_url(issue.key),
        "summary": issue.summary,
        "status": issue.status.name,
        "status_css": _STATUS_CSS_CLASS.get(issue.status.category, "status-todo"),
        "assignee": assignee_name or "(unassigned)",
        "assignee_avatar": _avatar(assignee_name) if assignee_name else None,
        "priority": issue.priority or "N/A",
        "project_key": issue.project_key,
        "issue_type": issue.issue_type,
        "created_at": issue.created_at.strftime("%Y-%m-%d"),
        "updated_at": issue.updated_at.strftime("%Y-%m-%d %H:%M"),
        "due_date": issue.due_date.isoformat() if issue.due_date else None,
        "due_date_css": _DUE_DATE_TEXT_CSS.get(due_state, ""),
        "due_row_css": _DUE_DATE_ROW_CSS.get(due_state, ""),
        "completed_at": issue.completed_at.strftime("%Y-%m-%d %H:%M") if issue.completed_at else None,
        "parent_key": issue.parent_key,
        "parent_url": _issue_url(issue.parent_key) if issue.parent_key else None,
        "parent_summary": issue.parent_summary,
    }


def epic_view(report: EpicReport) -> Dict[str, Any]:
    return {
        "epic": issue_row(report.epic),
        "children": [issue_row(child) for child in report.children],
        "status_counts": sorted(report.status_counts.items()),
    }


_GROUP_ACCENT_PALETTE = ["#0073ea", "#a25ddc", "#00c875", "#fdab3d", "#e2445c", "#66ccff"]


def unticketed_by_member(items: List[TrackingItem]) -> Dict[str, List[TrackingItem]]:
    """Groups the tracking items that were routed to a roster member, so
    the workload page can show each person theirs.

    Only items still being chased: a tracking item that's been closed (or
    parked) is no longer work waiting for a ticket, and leaving it on
    someone's workload would make the block impossible to trust. Items
    with no member are simply absent — nowhere to put them.
    """
    grouped: Dict[str, List[TrackingItem]] = {}
    for item in items:
        if item.member_account_id and item.is_active:
            grouped.setdefault(item.member_account_id, []).append(item)
    return grouped


def workload_view(
    report: WorkloadReport, unticketed: List[TrackingItem] = ()
) -> Dict[str, Any]:
    allocation = sorted(report.allocation_by_project.items())
    today = date.today()

    backlog_by_project: Dict[str, List[Issue]] = {}
    for issue in report.backlog_issues:
        backlog_by_project.setdefault(issue.project_key, []).append(issue)

    backlog_groups = [
        {
            "project_key": project_key,
            "accent": _GROUP_ACCENT_PALETTE[index % len(_GROUP_ACCENT_PALETTE)],
            "issues": [issue_row(issue) for issue in issues],
        }
        for index, (project_key, issues) in enumerate(sorted(backlog_by_project.items()))
    ]

    return {
        "person": {
            "display_name": report.person.display_name,
            "account_id": report.person.account_id,
            "avatar": _avatar(report.person.display_name),
        },
        # Only the count is ever rendered for the full list (the page shows
        # issues through the active/backlog groups below), so don't pay for
        # a whole second set of row dicts.
        "issue_count": len(report.issues),
        "allocation_by_project": allocation,
        # Hand-kept follow-ups that never became tickets, so they can't
        # come out of `report` (which only knows what Jira returned).
        "unticketed_items": [_tracking_row(item, today) for item in unticketed],
        "unticketed_count": len(unticketed),
        "completed_issues": [issue_row(issue) for issue in report.completed_issues],
        "completed_count": len(report.completed_issues),
        "active_issues": [issue_row(issue) for issue in report.active_issues],
        "backlog_groups_by_project": backlog_groups,
        "backlog_count": len(report.backlog_issues),
    }


@lru_cache(maxsize=1)
def _overview_rank_table() -> Dict[str, int]:
    """Cached like _jira_domain: read once per process, not once per row."""
    return overview_project_rank_from_env()


def _overview_project_rank(project_key: str) -> tuple:
    table = _overview_rank_table()
    return (table.get(project_key, len(table)), project_key)


def weekly_overview_markdown(reports: List[WorkloadReport], intro: str = "") -> str:
    """Drafts the weekly "Ongoing Project" status update: one section per
    member, that member's active (Running/Reviewing) tickets ranked by
    project (the OVERVIEW_PROJECT_RANK order, everything else after) then
    by due date.

    Each ticket with a due date gets an auto-filled "人力:N天,完成日:..."
    line (N = days between created_at and due_date); issues with no due
    date get no such line at all — there's nothing honest to compute, so
    it's left fully blank rather than filled with a placeholder. The real
    status write-up ("優先處理 => ...") is left for a human to type in
    after, since that's a judgment call Jira has no field for.

    `intro` is arbitrary saved text (e.g. a standing strategy note) that,
    when present, is pasted in verbatim above the "Ongoing Project" list.
    """
    lines: List[str] = []
    if intro.strip():
        lines.append(intro.strip())
        lines.append("")

    lines.append("Ongoing Project")

    for report in reports:
        if not report.active_issues:
            continue

        ordered = sorted(
            report.active_issues,
            key=lambda issue: (_overview_project_rank(issue.project_key), issue.due_date or date.max),
        )

        lines.append(report.person.display_name)
        for issue in ordered:
            lines.append(f"- {_issue_url(issue.key)}")
            if issue.due_date:
                days = (issue.due_date - issue.created_at.date()).days
                lines.append(f"   - 人力:{days}天,完成日:{issue.due_date.isoformat()}")
        lines.append("")

    return "\n".join(lines)


# The window deliberately reaches into the past: an overdue or
# just-finished-late span is only legible if the axis has room to draw it.
# Seven days back always covers the current week's Monday (six days back at
# the most, on a Sunday), which is the span a weekly review looks at.
_GANTT_PAST_DAYS = 7
_GANTT_FUTURE_DAYS = 14
_GANTT_WINDOW_DAYS = _GANTT_PAST_DAYS + _GANTT_FUTURE_DAYS
_GANTT_MIN_BAR_PCT = 3.0


def gantt_view(reports: List[WorkloadReport]) -> Dict[str, Any]:
    """This week's finished work plus everything still active
    (Running/Reviewing), on a three-week axis — last week plus the next
    two — grouped by member, with today marked.

    Each bar spans the issue's own start date to its due date, clipped to
    the window, so a three-day task reads as a three-day bar sitting where
    it falls. Jira's "Start date" is optional; when it is missing the
    creation date stands in for it, which matches the 人力 figure in the
    weekly overview.

      - "completed": finished this week — the one status whose bar ends on
        what actually happened (the completion timestamp) rather than on a
        plan, so a ticket delivered early reads shorter than its due date
        promised, and a late one reads longer.
      - "overdue": due date already passed — drawn at its real length, to
        the left of the today marker.
      - "due_soon": due date lands inside the window.
      - "beyond_window": due date is further out than the window — the bar
        runs to the right edge, flagged so the template can mark it as
        continuing past the visible range.
      - "open_ended": no due date at all — bar runs from its start to the
        right edge, flagged separately (still running, no deadline).

    Anything older than the left edge is clipped to it, so a long-overdue
    or long-running item shows as starting at the edge rather than
    disappearing.
    """
    today = date.today()
    window_start = today - timedelta(days=_GANTT_PAST_DAYS)
    window_end = today + timedelta(days=_GANTT_FUTURE_DAYS)

    def _pct(day: date) -> float:
        """Where a day's *left* edge sits on the axis, unrounded — callers
        subtract these to get a width, and rounding first leaves a bar a
        hundredth of a percent short of the day it should end on.
        """
        offset_days = (day - window_start).days
        return min(max(offset_days, 0), _GANTT_WINDOW_DAYS) / _GANTT_WINDOW_DAYS * 100

    def _start_of(issue: Issue) -> date:
        return issue.start_date or issue.created_at.date()

    def _row(
        issue: Issue, status: str, left_pct: float, width_pct: float, date_label: str
    ) -> Dict[str, Any]:
        """Shared tail of every bar: fit it inside the track, then render.

        A span that lands on the right edge, or one whose dates are the
        wrong way round, still has to be visible — so pull the left edge
        back far enough for the minimum bar to fit rather than letting a
        bar at 100% hang off the track.
        """
        left_pct = min(left_pct, 100.0 - _GANTT_MIN_BAR_PCT)
        width_pct = min(max(width_pct, _GANTT_MIN_BAR_PCT), 100.0 - left_pct)

        return {
            "key": issue.key,
            "url": _issue_url(issue.key),
            "summary": issue.summary,
            "status": status,
            "left_pct": round(left_pct, 2),
            "width_pct": round(width_pct, 2),
            "date_label": date_label,
        }

    def _span_width(start: date, end: date, left_pct: float) -> float:
        """Width of an inclusive start..end span whose left edge is known.

        Jira's dates are inclusive — work runs through the end of the last
        day — so the bar reaches the *next* day's left edge: a 09/07~09/09
        task is three days wide, and a same-day task is one day wide
        rather than zero. _pct clamps to the window, so an end past the
        right edge simply lands on it.
        """
        return _pct(end + timedelta(days=1)) - left_pct

    def _completion_date(issue: Issue) -> date:
        """When the work actually finished.

        `completed_at` is the truth here, but it is only as present as
        Jira's status history: fall back to the due date, then to today,
        so a finished ticket still gets a bar instead of vanishing.
        """
        if issue.completed_at is not None:
            return issue.completed_at.date()
        return issue.due_date or today

    def _completed_bar(issue: Issue) -> Dict[str, Any]:
        start = _start_of(issue)
        # Bulk-closed housekeeping tickets can carry a start date later
        # than the moment they were closed; clamp rather than draw a
        # backwards bar.
        end = max(_completion_date(issue), start)
        left_pct = _pct(start)
        return _row(
            issue,
            "completed",
            left_pct,
            _span_width(start, end, left_pct),
            f"{start.isoformat()} ~ {end.isoformat()}(已完成)",
        )

    def _bar(issue: Issue) -> Dict[str, Any]:
        due = issue.due_date
        start = _start_of(issue)
        left_pct = _pct(start)

        if due is None:
            status = "open_ended"
            width_pct = 100.0 - left_pct
            date_label = f"{start.isoformat()} 起,無到期日"
        else:
            if due < today:
                status = "overdue"
                date_label = f"{start.isoformat()} ~ {due.isoformat()}(已逾期)"
            elif due > window_end:
                status = "beyond_window"
                date_label = f"{start.isoformat()} ~ {due.isoformat()}(超過兩週)"
            else:
                status = "due_soon"
                date_label = f"{start.isoformat()} ~ {due.isoformat()}"
            width_pct = _span_width(start, due, left_pct)

        return _row(issue, status, left_pct, width_pct, date_label)

    # Overdue bars first, then by due date — ordered on the issues
    # themselves, so the rendered rows never need a scratch sort key
    # threaded through (and deleted from) the view dicts.
    def _row_order(issue: Issue) -> tuple:
        due = issue.due_date
        is_overdue = due is not None and due < today
        return (not is_overdue, due or date.max)

    groups = []
    for report in reports:
        if not report.active_issues and not report.completed_issues:
            continue

        # Finished work first, in the same order the member's table lists
        # it, so the two panels can be read against each other.
        entries = [_completed_bar(issue) for issue in report.completed_issues]
        entries += [_bar(issue) for issue in sorted(report.active_issues, key=_row_order)]

        groups.append(
            {
                "member": report.person.display_name,
                "avatar": _avatar(report.person.display_name),
                "rows": entries,
            }
        )

    return {
        "groups": groups,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "today": today.isoformat(),
        "today_pct": round(_pct(today), 2),
    }


def _member_card(person: Person) -> Dict[str, Any]:
    return {
        "account_id": person.account_id,
        "display_name": person.display_name,
        "email": person.email or "",
        "avatar": _avatar(person.display_name),
    }


def member_roster_view(members: List[Person]) -> List[Dict[str, Any]]:
    """Full roster, for the member-management page's list/rename/delete."""
    return [_member_card(person) for person in members]


def member_candidates_view(candidates: List[Person]) -> List[Dict[str, Any]]:
    """Jira search results not yet on the roster, for the "add member" form."""
    return [_member_card(person) for person in candidates]


def member_options_view(members: List[Person]) -> List[Dict[str, str]]:
    """Minimal (account_id, display_name) pairs for a <select> on other pages."""
    return [{"account_id": person.account_id, "display_name": person.display_name} for person in members]


def comments_view(comments: List[Comment]) -> List[Dict[str, Any]]:
    return [
        {
            "author": comment.author,
            "body": comment.body,
            "created_at": comment.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for comment in comments
    ]


def team_risk_view(report: TeamRiskReport) -> Dict[str, Any]:
    return {
        "overdue": [issue_row(issue) for issue in report.overdue],
        "unassigned": [issue_row(issue) for issue in report.unassigned],
        "stale": [issue_row(issue) for issue in report.stale],
    }


def weekly_view(report: WeeklyReport) -> Dict[str, Any]:
    return {
        "person": {
            "display_name": report.person.display_name,
            "avatar": _avatar(report.person.display_name),
        },
        "window_days": report.window_days,
        "completed": [issue_row(issue) for issue in report.completed],
        "in_progress": [issue_row(issue) for issue in report.in_progress],
        "stuck": [issue_row(issue) for issue in report.stuck],
    }


# --- 專案盤查 -----------------------------------------------------------

_URGENCY_CSS = {"危急": "urgency-critical", "高": "urgency-high", "中": "urgency-medium"}
_DEFAULT_URGENCY_CSS = "urgency-low"

# Only these three; anything else falls back to the flat list rather than
# erroring, so a hand-edited query string can't break the page.
GROUP_BY_CHOICES = ("none", "assignee", "type")
_GROUP_BY_LABELS = {"none": "不分組", "assignee": "依負責人", "type": "依類型"}


def audit_group_by_options() -> List[Dict[str, str]]:
    return [{"value": value, "label": _GROUP_BY_LABELS[value]} for value in GROUP_BY_CHOICES]


def normalize_group_by(raw: Optional[str]) -> str:
    return raw if raw in GROUP_BY_CHOICES else "none"


def _audit_row(entry: AuditEntry) -> Dict[str, Any]:
    row = issue_row(entry.issue)
    row.update(
        {
            "urgency_score": entry.score,
            "urgency_label": entry.level,
            "urgency_css": _URGENCY_CSS.get(entry.level, _DEFAULT_URGENCY_CSS),
            # Joined here rather than in the template: it's presentation,
            # and it keeps the macro from needing a loop inside a cell.
            "urgency_reasons": "、".join(entry.reasons) or "—",
            "stale_days": entry.stale_days,
            "is_overdue": bool(entry.overdue_days),
        }
    )
    return row


def _group_key(entry: AuditEntry, group_by: str) -> str:
    if group_by == "assignee":
        return entry.issue.assignee.display_name if entry.issue.assignee else "未認領"
    return entry.issue.issue_type or "未分類"


def _audit_groups(entries: List[AuditEntry], group_by: str) -> List[Dict[str, Any]]:
    """One unnamed group when ungrouped, so the template renders the same
    table markup either way instead of branching on the mode.
    """
    if group_by == "none":
        if not entries:
            return []
        return [{"title": None, "avatar": None, "accent": None, "rows": [_audit_row(e) for e in entries]}]

    buckets: Dict[str, List[AuditEntry]] = {}
    for entry in entries:
        buckets.setdefault(_group_key(entry, group_by), []).append(entry)

    # Groups ordered by their most urgent member, so the person (or issue
    # type) that needs attention first is at the top — a group ordered
    # alphabetically would bury it.
    ordered = sorted(buckets.items(), key=lambda pair: (-pair[1][0].score, pair[0]))

    return [
        {
            "title": title,
            "avatar": _avatar(title) if group_by == "assignee" else None,
            "accent": _GROUP_ACCENT_PALETTE[index % len(_GROUP_ACCENT_PALETTE)],
            "rows": [_audit_row(entry) for entry in group_entries],
        }
        for index, (title, group_entries) in enumerate(ordered)
    ]


def project_audit_view(report: ProjectAuditReport, group_by: str = "none") -> Dict[str, Any]:
    group_by = normalize_group_by(group_by)
    stats = report.stats

    return {
        "window_days": report.window_days,
        "project_label": "/".join(report.project_keys),
        "group_by": group_by,
        "grouped": group_by != "none",
        "stats": {
            "total": stats.total,
            "open_count": stats.open_count,
            "done_count": stats.done_count,
            "done_rate": stats.done_rate,
            "overdue_count": stats.overdue_count,
            "high_priority_count": stats.high_priority_count,
            "unassigned_count": stats.unassigned_count,
            "no_due_date_count": stats.no_due_date_count,
            "stale_count": stats.stale_count,
            "stale_days": report.gaps.stale_days,
            "median_stale_days": stats.median_stale_days,
        },
        "groups": _audit_groups(report.open_entries, group_by),
        "done": [issue_row(issue) for issue in report.done_issues],
    }


# --- 追蹤事項 -----------------------------------------------------------
#
# Nothing below may reach for _issue_url/_jira_domain. Those call
# JiraConfig.from_env() and raise when it's missing, which would drag the
# one deliberately Jira-free page back into needing credentials.

# Insertion order is the display order, and drives every <select> on the page.
_TRACKING_STATUS_LABELS = {
    TrackingStatus.TODO: "待處理",
    TrackingStatus.IN_PROGRESS: "進行中",
    TrackingStatus.WAITING: "等待回覆",
    TrackingStatus.DONE: "已完成",
    TrackingStatus.ON_HOLD: "已擱置",
}

_TRACKING_STATUS_CSS = {
    TrackingStatus.TODO: "status-todo",
    TrackingStatus.IN_PROGRESS: "status-progress",
    TrackingStatus.WAITING: "status-waiting",
    TrackingStatus.DONE: "status-done",
    TrackingStatus.ON_HOLD: "status-hold",
}

_TRACKING_PRIORITY_LABELS = {
    TrackingPriority.HIGH: "高",
    TrackingPriority.MEDIUM: "中",
    TrackingPriority.LOW: "低",
}

_TRACKING_PRIORITY_CSS = {
    TrackingPriority.HIGH: "priority-high",
    TrackingPriority.MEDIUM: "priority-medium",
    TrackingPriority.LOW: "priority-low",
}


def tracking_status_options() -> List[Dict[str, str]]:
    """(value, label) pairs for the status <select>, in display order."""
    return [{"value": status.value, "label": label} for status, label in _TRACKING_STATUS_LABELS.items()]


def tracking_priority_options() -> List[Dict[str, str]]:
    return [
        {"value": priority.value, "label": label}
        for priority, label in _TRACKING_PRIORITY_LABELS.items()
    ]


# Shared empty default so the mapping is never accidentally mutated.
_NO_MEMBER_NAMES: Dict[str, str] = {}


def _safe_link(raw: Optional[str]) -> Optional[str]:
    """Only http(s) URLs reach an href.

    The link is free text a person types, and a hand-built POST could put
    `javascript:...` in there — which would then be a real XSS the moment
    someone clicks the row title.
    """
    if not raw:
        return None
    candidate = raw.strip()
    if candidate.startswith("http://") or candidate.startswith("https://"):
        return candidate
    return None


# Only http(s), and only the ASCII characters a URL is actually built from
# (RFC 3986's unreserved + reserved + percent-escape set). A broader "not
# whitespace" match swallows the Chinese prose that follows a link pasted
# mid-sentence — "…/browse/ABC-123。後續再談" became one 30-character link
# whose href was broken.
_NOTE_URL_PATTERN = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+")
# Sentence-enders (both alphabets) that a URL pasted mid-sentence collects.
_NOTE_URL_TRAILING = ".,;:!?)]}、。,;:!?)】」"
# Roughly how much of a URL can sit in a note line before it stops being
# readable text and starts being a wall of characters.
_NOTE_LINK_LABEL_MAX = 40


def _link_label(url: str) -> str:
    """A short, readable stand-in for a URL.

    Keeps the host and as many whole path segments as fit, then marks the
    rest with an ellipsis — "docs.google.com/spreadsheets/d/…" says what
    the link is far better than 90 characters of document id, and a
    URL-shaped string with no spaces in it cannot wrap, so printing it in
    full drags the whole table wider than the page.

    The query string and fragment are dropped from the label entirely
    (they are the least informative part); the href keeps the real URL.
    """
    parsed = urlsplit(url)
    host = parsed.netloc[len("www.") :] if parsed.netloc.startswith("www.") else parsed.netloc
    label = host or url

    for segment in (segment for segment in parsed.path.split("/") if segment):
        if len(label) + len(segment) + 1 > _NOTE_LINK_LABEL_MAX:
            return f"{label}/…"
        label = f"{label}/{segment}"

    if parsed.query or parsed.fragment:
        label = f"{label}?…" if len(label) + 2 <= _NOTE_LINK_LABEL_MAX else f"{label}…"
    return label


def _note_segments(text: str) -> List[Dict[str, str]]:
    """Splits a note into runs of plain text and links, so the template can
    render a URL as a short label instead of printing it in full.

    Done here rather than with a Jinja filter or client-side script
    because the label has to be chosen from the parsed URL, and the text
    around it must stay escaped like any other user input.
    """
    segments: List[Dict[str, str]] = []
    cursor = 0

    for match in _NOTE_URL_PATTERN.finditer(text):
        url = match.group().rstrip(_NOTE_URL_TRAILING)
        if not url:
            continue
        if match.start() > cursor:
            segments.append({"text": text[cursor : match.start()]})
        segments.append({"text": _link_label(url), "url": url})
        cursor = match.start() + len(url)

    if cursor < len(text):
        segments.append({"text": text[cursor:]})
    return segments


def _tracking_row(
    item: TrackingItem, today: date, member_names: Dict[str, str] = _NO_MEMBER_NAMES
) -> Dict[str, Any]:
    """Carries both the display text and the raw enum/ISO values, because
    the same row feeds a read-only cell *and* the pre-filled edit form
    hidden underneath it.

    `member_names` turns a routed account id into something readable;
    callers that have no roster on hand (or don't render that badge) can
    leave it out and get a blank name with the id still intact.
    """
    return {
        "id": item.id,
        "item": item.item,
        "owner": item.owner or "",
        "owner_avatar": _avatar(item.owner) if item.owner else None,
        "status_value": item.status.value,
        "status_label": _TRACKING_STATUS_LABELS[item.status],
        "status_css": _TRACKING_STATUS_CSS[item.status],
        "priority_value": item.priority.value,
        "priority_label": _TRACKING_PRIORITY_LABELS[item.priority],
        "priority_css": _TRACKING_PRIORITY_CSS[item.priority],
        "due_date": item.due_date.isoformat() if item.due_date else "",
        "is_overdue": bool(item.is_active and item.due_date and item.due_date < today),
        # The same macro renders both halves of the page, and the one-click
        # action flips with this: 完成 for something still being chased,
        # 重新追蹤 for something that turned out not to be finished.
        "is_active": item.is_active,
        "member_account_id": item.member_account_id or "",
        "member_name": member_names.get(item.member_account_id or "", ""),
        "link": _safe_link(item.link),
        # Oldest first, matching the order they were written in — the cell
        # reads as a log, so the newest line sits closest to 最後更新.
        "notes": [
            {
                "text": note.text,
                "segments": _note_segments(note.text),
                "created_at": note.created_at.strftime("%Y-%m-%d %H:%M"),
            }
            for note in item.notes
        ],
        "updated_at": item.updated_at.strftime("%Y-%m-%d %H:%M"),
    }


def tracking_view(
    items: List[TrackingItem], member_names: Dict[str, str] = _NO_MEMBER_NAMES
) -> Dict[str, Any]:
    """Splits the (already ordered) list into what still needs chasing and
    what's been closed out, so the template can tuck the latter away.
    """
    today = date.today()
    active = [item for item in items if item.is_active]
    closed = sorted((item for item in items if not item.is_active), key=lambda i: i.updated_at, reverse=True)

    return {
        "active": [_tracking_row(item, today, member_names) for item in active],
        "closed": [_tracking_row(item, today, member_names) for item in closed],
        "counts": {
            "active": len(active),
            "overdue": sum(1 for item in active if item.due_date and item.due_date < today),
            "waiting": sum(1 for item in active if item.status == TrackingStatus.WAITING),
            "closed": len(closed),
        },
    }
