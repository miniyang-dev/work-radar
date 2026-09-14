"""Formats application-layer reports as plain text for the terminal.

Kept separate from the use cases themselves: a use case answers "what is
true," a presenter answers "how do I show it." Swapping this module for a
JSON or Slack-message renderer never touches EpicReportService,
WorkloadReportService, or StaleIssueFinder.
"""
from __future__ import annotations

from work_radar.application.cycle_time import CycleTimeReport
from work_radar.application.epic_report import EpicReport
from work_radar.application.risk_scan import TeamRiskReport
from work_radar.application.weekly_report import WeeklyReport
from work_radar.application.workload_report import WorkloadReport
from work_radar.domain.models import Issue


def render_issue_line(issue: Issue, indent: str = "  ") -> str:
    assignee = issue.assignee.display_name if issue.assignee else "(unassigned)"
    parent = f" (parent: {issue.parent_key} {issue.parent_summary})" if issue.parent_key else ""
    return (
        f"{indent}[{issue.key}] {issue.summary}{parent}\n"
        f"{indent}    project={issue.project_key}  type={issue.issue_type}  "
        f"status={issue.status.name}  assignee={assignee}  "
        f"priority={issue.priority or 'N/A'}  updated={issue.updated_at.isoformat()}"
    )


def render_epic_report(report: EpicReport) -> str:
    epic = report.epic
    lines = [
        f"=== {epic.key}: {epic.summary} ===",
        f"Status: {epic.status.name}",
        f"Assignee: {epic.assignee.display_name if epic.assignee else '(unassigned)'}",
        f"Priority: {epic.priority or 'N/A'}",
        "",
        f"=== {len(report.children)} child issue(s) ===",
    ]
    lines.extend(render_issue_line(child) for child in report.children)
    lines.append("")
    lines.append("=== Status summary ===")
    for status, count in sorted(report.status_counts.items()):
        lines.append(f"  {status}: {count}")
    return "\n".join(lines)


def render_workload_report(report: WorkloadReport) -> str:
    lines = [
        f"=== Issues assigned to {report.person.display_name} ===",
        "",
        f"{len(report.issues)} open issue(s):",
        "",
    ]
    lines.extend(render_issue_line(issue) for issue in report.issues)
    if report.allocation_by_project:
        lines.append("")
        lines.append("=== Allocation by project ===")
        for project, percentage in sorted(report.allocation_by_project.items()):
            lines.append(f"  {project}: {percentage}%")
    return "\n".join(lines)


def render_stale_issues(issues: list[Issue], threshold_days: int) -> str:
    lines = [f"=== {len(issues)} issue(s) stale for {threshold_days}+ days ===", ""]
    lines.extend(render_issue_line(issue) for issue in issues)
    return "\n".join(lines)


def render_team_risk_report(report: TeamRiskReport, project_keys: list[str]) -> str:
    lines = [f"=== Risk scan: {', '.join(project_keys)} ===", ""]

    lines.append(f"--- Overdue ({len(report.overdue)}) ---")
    lines.extend(render_issue_line(issue) for issue in report.overdue)
    lines.append("")

    lines.append(f"--- Unassigned ({len(report.unassigned)}) ---")
    lines.extend(render_issue_line(issue) for issue in report.unassigned)
    lines.append("")

    lines.append(f"--- Stale ({len(report.stale)}) ---")
    lines.extend(render_issue_line(issue) for issue in report.stale)

    return "\n".join(lines)


def _format_days(value: float | None) -> str:
    """Renders a day count, keeping a genuine 0.0 distinct from "unknown".

    `value or "N/A"` would collapse the two: an issue created and finished
    inside the same day rounds to 0.0, which is a real measurement, not a
    missing one.
    """
    return "N/A" if value is None else str(value)


def render_cycle_time_report(report: CycleTimeReport, project_keys: list[str], window_days: int) -> str:
    lines = [
        f"=== Cycle time: {', '.join(project_keys)} (last {window_days} day(s), {len(report.results)} issue(s)) ===",
        f"Average lead time: {_format_days(report.average_lead_time_days)} day(s)",
        f"Average cycle time: {_format_days(report.average_cycle_time_days)} day(s)",
        "",
    ]
    for result in report.results:
        lines.append(
            f"  [{result.issue_key}] lead={_format_days(result.lead_time_days)}d  "
            f"cycle={_format_days(result.cycle_time_days)}d"
        )
    return "\n".join(lines)


def render_weekly_report(report: WeeklyReport) -> str:
    lines = [f"=== Weekly report: {report.person.display_name} (last {report.window_days} day(s)) ===", ""]

    lines.append(f"--- Completed ({len(report.completed)}) ---")
    lines.extend(render_issue_line(issue) for issue in report.completed)
    lines.append("")

    lines.append(f"--- In progress ({len(report.in_progress)}) ---")
    lines.extend(render_issue_line(issue) for issue in report.in_progress)
    lines.append("")

    lines.append(f"--- Stuck ({len(report.stuck)}) ---")
    lines.extend(render_issue_line(issue) for issue in report.stuck)

    return "\n".join(lines)
