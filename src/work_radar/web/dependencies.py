"""Composition root for the web adapter.

Mirrors cli/main.py's role: the only module here allowed to know about
every layer at once. Built lazily and cached so the Jira HTTP session
(and its resolved cloud id) is reused across requests instead of
reconnecting every time.
"""
from __future__ import annotations

from functools import lru_cache

from work_radar.application.epic_report import EpicReportService
from work_radar.application.issue_comments import IssueCommentService
from work_radar.application.member_roster import MemberRosterService
from work_radar.application.project_audit import ProjectAuditService
from work_radar.application.tracking_list import TrackingListService
from work_radar.application.weekly_report import WeeklyReportService
from work_radar.application.workload_report import WorkloadReportService
from work_radar.infrastructure.config import (
    JiraConfig,
    member_store_path_from_env,
    overview_note_path_from_env,
    tracking_store_path_from_env,
)
from work_radar.infrastructure.jira.http import JiraHttpClient
from work_radar.infrastructure.jira.repositories import (
    JiraIssueCommentRepository,
    JiraIssueHistoryRepository,
    JiraIssueRepository,
    JiraPersonRepository,
    JiraStatusCatalogRepository,
)
from work_radar.infrastructure.storage.json_member_repository import JsonMemberRepository
from work_radar.infrastructure.storage.json_tracking_repository import JsonTrackingRepository
from work_radar.infrastructure.storage.text_note_repository import TextNoteRepository


@lru_cache(maxsize=1)
def get_http_client() -> JiraHttpClient:
    return JiraHttpClient(JiraConfig.from_env())


@lru_cache(maxsize=1)
def get_issue_repository() -> JiraIssueRepository:
    return JiraIssueRepository(get_http_client())


@lru_cache(maxsize=1)
def get_person_repository() -> JiraPersonRepository:
    return JiraPersonRepository(get_http_client())


@lru_cache(maxsize=1)
def get_issue_history_repository() -> JiraIssueHistoryRepository:
    return JiraIssueHistoryRepository(get_http_client())


@lru_cache(maxsize=1)
def get_status_catalog_repository() -> JiraStatusCatalogRepository:
    return JiraStatusCatalogRepository(get_http_client())


@lru_cache(maxsize=1)
def get_issue_comment_repository() -> JiraIssueCommentRepository:
    return JiraIssueCommentRepository(get_http_client())


@lru_cache(maxsize=1)
def get_issue_comment_service() -> IssueCommentService:
    return IssueCommentService(get_issue_comment_repository())


@lru_cache(maxsize=1)
def get_epic_report_service() -> EpicReportService:
    return EpicReportService(get_issue_repository())


@lru_cache(maxsize=1)
def get_workload_report_service() -> WorkloadReportService:
    return WorkloadReportService(get_issue_repository(), get_person_repository())


@lru_cache(maxsize=1)
def get_project_audit_service() -> ProjectAuditService:
    return ProjectAuditService(get_issue_repository())


@lru_cache(maxsize=1)
def get_member_repository() -> JsonMemberRepository:
    return JsonMemberRepository(member_store_path_from_env())


@lru_cache(maxsize=1)
def get_overview_note_repository() -> TextNoteRepository:
    return TextNoteRepository(overview_note_path_from_env())


@lru_cache(maxsize=1)
def get_member_roster_service() -> MemberRosterService:
    return MemberRosterService(get_member_repository(), get_person_repository())


@lru_cache(maxsize=1)
def get_weekly_report_service() -> WeeklyReportService:
    return WeeklyReportService(
        get_issue_repository(),
        get_person_repository(),
        get_issue_history_repository(),
        get_status_catalog_repository(),
    )


# Neither of the two below touches get_http_client(), and that's the whole
# point: the 追蹤事項 page is the one screen that renders with no Jira
# credentials configured at all.
@lru_cache(maxsize=1)
def get_tracking_repository() -> JsonTrackingRepository:
    return JsonTrackingRepository(tracking_store_path_from_env())


@lru_cache(maxsize=1)
def get_tracking_list_service() -> TrackingListService:
    return TrackingListService(get_tracking_repository())
