"""Composition root.

This is the one place allowed to know about every layer at once: it reads
configuration, builds the concrete Jira adapters, injects them into the
application services, and renders the result. Nothing below this module
imports anything above it.
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

from work_radar.application.cycle_time import DEFAULT_CYCLE_TIME_WINDOW_DAYS, CycleTimeReportService
from work_radar.application.epic_report import EpicReportService
from work_radar.application.risk_scan import TeamRiskReportService, TeamRiskScanner
from work_radar.application.stall_detection import DEFAULT_STALL_THRESHOLD_DAYS, StaleIssueFinder
from work_radar.application.weekly_report import DEFAULT_WEEKLY_WINDOW_DAYS, WeeklyReportService
from work_radar.application.workload_report import WorkloadReportService
from work_radar.cli.presenters import (
    render_cycle_time_report,
    render_epic_report,
    render_stale_issues,
    render_team_risk_report,
    render_weekly_report,
    render_workload_report,
)
from work_radar.domain.exceptions import WorkRadarError
from work_radar.infrastructure.config import ConfigurationError, JiraConfig
from work_radar.infrastructure.jira.errors import JiraApiError
from work_radar.infrastructure.jira.http import JiraHttpClient
from work_radar.infrastructure.jira.repositories import (
    JiraIssueHistoryRepository,
    JiraIssueRepository,
    JiraPersonRepository,
    JiraStatusCatalogRepository,
)


@dataclass(frozen=True)
class _Adapters:
    """The concrete Jira adapters, built once and handed to whichever
    command needs them — so each command handler states its own
    dependencies instead of every one of them being wired inline in a
    single if/elif chain.
    """

    issues: JiraIssueRepository
    people: JiraPersonRepository
    history: JiraIssueHistoryRepository
    status_catalogs: JiraStatusCatalogRepository

    @classmethod
    def build(cls, config: JiraConfig) -> "_Adapters":
        http_client = JiraHttpClient(config)
        return cls(
            issues=JiraIssueRepository(http_client),
            people=JiraPersonRepository(http_client),
            history=JiraIssueHistoryRepository(http_client),
            status_catalogs=JiraStatusCatalogRepository(http_client),
        )


def _project_keys(raw: str) -> list[str]:
    return [key.strip() for key in raw.split(",") if key.strip()]


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError("must be 1 or greater")
    return value


def _run_epic(args: argparse.Namespace, adapters: _Adapters) -> str:
    report = EpicReportService(adapters.issues).build_report(args.key)
    return render_epic_report(report)


def _run_workload(args: argparse.Namespace, adapters: _Adapters) -> str:
    report = WorkloadReportService(adapters.issues, adapters.people).build_report(args.name)
    return render_workload_report(report)


def _run_stale(args: argparse.Namespace, adapters: _Adapters) -> str:
    workload = WorkloadReportService(adapters.issues, adapters.people).build_report(args.name)
    stale_issues = StaleIssueFinder(threshold_days=args.days).find_stale(
        workload.issues, as_of=datetime.now(timezone.utc)
    )
    return render_stale_issues(stale_issues, args.days)


def _run_risk(args: argparse.Namespace, adapters: _Adapters) -> str:
    project_keys = _project_keys(args.projects)
    scanner = TeamRiskScanner(stale_finder=StaleIssueFinder(threshold_days=args.stale_days))
    report = TeamRiskReportService(adapters.issues, scanner=scanner).build_report(
        project_keys, as_of=datetime.now(timezone.utc)
    )
    return render_team_risk_report(report, project_keys)


def _run_cycle_time(args: argparse.Namespace, adapters: _Adapters) -> str:
    project_keys = _project_keys(args.projects)
    service = CycleTimeReportService(adapters.issues, adapters.history, adapters.status_catalogs)
    report = service.build_report(project_keys, window_days=args.window_days)
    return render_cycle_time_report(report, project_keys, args.window_days)


def _run_weekly(args: argparse.Namespace, adapters: _Adapters) -> str:
    service = WeeklyReportService(
        adapters.issues, adapters.people, adapters.history, adapters.status_catalogs
    )
    report = service.build_report(
        args.name, as_of=datetime.now(timezone.utc), window_days=args.window_days
    )
    return render_weekly_report(report)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="work-radar",
        description="Scan Jira for stalled work items and per-person workload.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    epic_parser = subparsers.add_parser("epic", help="Report on an Epic and its children.")
    epic_parser.add_argument("key", help="Epic issue key, e.g. ABC-123")
    epic_parser.set_defaults(handler=_run_epic)

    workload_parser = subparsers.add_parser("workload", help="List a person's open issues.")
    workload_parser.add_argument("name", help="Display name (or partial match) of the assignee")
    workload_parser.set_defaults(handler=_run_workload)

    stale_parser = subparsers.add_parser("stale", help="Find a person's open issues that haven't moved in a while.")
    stale_parser.add_argument("name", help="Display name (or partial match) of the assignee")
    stale_parser.add_argument(
        "--days",
        type=_positive_int,
        default=DEFAULT_STALL_THRESHOLD_DAYS,
        help=f"Stall threshold in days (default: {DEFAULT_STALL_THRESHOLD_DAYS})",
    )
    stale_parser.set_defaults(handler=_run_stale)

    risk_parser = subparsers.add_parser("risk", help="Scan a set of projects for overdue/unassigned/stale issues.")
    risk_parser.add_argument("projects", help="Comma-separated project keys, e.g. ABC,DEF")
    risk_parser.add_argument("--stale-days", type=_positive_int, default=DEFAULT_STALL_THRESHOLD_DAYS)
    risk_parser.set_defaults(handler=_run_risk)

    cycle_parser = subparsers.add_parser("cycle-time", help="Report lead/cycle time for recently-done issues.")
    cycle_parser.add_argument("projects", help="Comma-separated project keys, e.g. ABC,DEF")
    cycle_parser.add_argument("--window-days", type=_positive_int, default=DEFAULT_CYCLE_TIME_WINDOW_DAYS)
    cycle_parser.set_defaults(handler=_run_cycle_time)

    weekly_parser = subparsers.add_parser("weekly", help="Summarize a person's activity over the last N days.")
    weekly_parser.add_argument("name", help="Display name (or partial match) of the assignee")
    weekly_parser.add_argument("--window-days", type=_positive_int, default=DEFAULT_WEEKLY_WINDOW_DAYS)
    weekly_parser.set_defaults(handler=_run_weekly)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    # So adapter-level warnings (e.g. a search hitting its page cap and
    # returning truncated results) actually reach the terminal.
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    try:
        config = JiraConfig.from_env()
    except ConfigurationError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 1

    try:
        print(args.handler(args, _Adapters.build(config)))
    except (WorkRadarError, JiraApiError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
