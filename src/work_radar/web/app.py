"""FastAPI adapter.

A second "driver" alongside cli/main.py, reusing the exact same
application services — this module (and dependencies.py) is the only
place that knows both "the web exists" and "Jira exists" at once.
Nothing in application/ or domain/ changes to support this.
"""
import pathlib
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from work_radar.application.risk_scan import TeamRiskScanner
from work_radar.application.stall_detection import DEFAULT_STALL_THRESHOLD_DAYS, StaleIssueFinder
from work_radar.application.weekly_report import DEFAULT_WEEKLY_WINDOW_DAYS
from work_radar.application.workload_report import start_of_week
from work_radar.infrastructure.config import audit_project_keys_from_env
from work_radar.domain.exceptions import WorkRadarError
from work_radar.domain.models import Person, TrackingPriority, TrackingStatus
from work_radar.infrastructure.config import ConfigurationError
from work_radar.infrastructure.jira.errors import JiraApiError
from work_radar.web.dependencies import (
    get_epic_report_service,
    get_issue_comment_service,
    get_member_repository,
    get_member_roster_service,
    get_overview_note_repository,
    get_project_audit_service,
    get_tracking_list_service,
    get_weekly_report_service,
    get_workload_report_service,
)
from work_radar.web.presenters import (
    audit_group_by_options,
    comments_view,
    epic_view,
    gantt_view,
    member_candidates_view,
    member_options_view,
    member_roster_view,
    normalize_group_by,
    project_audit_view,
    team_risk_view,
    unticketed_by_member,
    tracking_priority_options,
    tracking_status_options,
    tracking_view,
    weekly_overview_markdown,
    weekly_view,
    workload_view,
)

_TEMPLATES_DIR = pathlib.Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

app = FastAPI(title="work-radar")

_KNOWN_ERRORS = (WorkRadarError, JiraApiError, ConfigurationError)

# Guards against a hand-edited query string turning into a nonsensical
# window: `?stale_days=0` marks every issue as stalled, and a negative
# value builds malformed JQL. The templates' own `min="1"` is only a
# client-side hint.
_MAX_WINDOW_DAYS = 365

_AUDIT_DEFAULT_WINDOW_DAYS = 90
_AUDIT_WINDOW_CHOICES = ((90, "近 3 個月"), (180, "近半年"), (365, "近一年"))


def _resolve_member(account_id: Optional[str]) -> Optional[Person]:
    """Looks up a roster member by id — lets weekly skip Jira name
    resolution entirely when the request came from the roster's <select>
    instead of the free-text name field.
    """
    if not account_id:
        return None
    return get_member_roster_service().get_member(account_id)


@app.get("/issue/{key}/comments", response_class=HTMLResponse)
def issue_comments(request: Request, key: str):
    """Renders an HTML fragment (not a full page) — fetched client-side and
    injected inline when someone expands an issue row's comments, so
    comments are only pulled from Jira on demand, not for every issue on
    every page load.
    """
    context = {}
    try:
        comments = get_issue_comment_service().list_comments(key)
        context["comments"] = comments_view(comments)
    except _KNOWN_ERRORS as error:
        context["error"] = str(error)
    return templates.TemplateResponse(request, "_comments_fragment.html", context)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/epic", response_class=HTMLResponse)
def epic(request: Request, key: Optional[str] = None):
    context = {"key": key or "", "active_nav": "epic"}
    if key:
        try:
            report = get_epic_report_service().build_report(key.strip())
            context["report"] = epic_view(report)
        except _KNOWN_ERRORS as error:
            context["error"] = str(error)
    return templates.TemplateResponse(request, "epic.html", context)


@app.get("/workload", response_class=HTMLResponse)
def workload(request: Request):
    """Shows every roster member's open workload at once, grouped by
    member — no name/selection step, since the roster (added via
    /members) already says who to show.
    """
    context = {"active_nav": "workload", "overview_note": ""}
    try:
        overview_note = get_overview_note_repository().read()
        context["overview_note"] = overview_note
        members = get_member_roster_service().list_members()
        reports = get_workload_report_service().build_reports_for_people(
            members, completed_since=start_of_week(date.today())
        )
        # The hand-kept follow-up list is local and cheap to read, and it
        # holds the work that has no ticket yet — the one thing a
        # Jira-derived report structurally cannot know about.
        unticketed = unticketed_by_member(get_tracking_list_service().list_items())
        context["reports"] = [
            workload_view(report, unticketed=unticketed.get(report.person.account_id, []))
            for report in reports
        ]
        context["gantt"] = gantt_view(reports)
        context["overview_markdown"] = weekly_overview_markdown(reports, intro=overview_note)
    except _KNOWN_ERRORS as error:
        context["error"] = str(error)
    return templates.TemplateResponse(request, "workload.html", context)


@app.post("/workload/overview-note")
def workload_overview_note(content: str = Form("")):
    get_overview_note_repository().write(content)
    return RedirectResponse(url="/workload", status_code=303)


@app.get("/members", response_class=HTMLResponse)
def members(request: Request, q: Optional[str] = None):
    # Building the roster service reaches for Jira configuration, so it
    # belongs inside the try alongside the calls themselves — otherwise a
    # missing .env renders a raw 500 here while every other page shows the
    # error banner.
    context = {"q": q or "", "active_nav": "members", "members": []}
    try:
        roster_service = get_member_roster_service()
        context["members"] = member_roster_view(roster_service.list_members())
        if q:
            context["candidates"] = member_candidates_view(roster_service.search_candidates(q.strip()))
    except _KNOWN_ERRORS as error:
        context["error"] = str(error)
    return templates.TemplateResponse(request, "members.html", context)


@app.post("/members/add")
def members_add(account_id: str = Form(...), display_name: str = Form(...), email: str = Form("")):
    get_member_roster_service().add_member(
        Person(account_id=account_id, display_name=display_name, email=email or None)
    )
    return RedirectResponse(url="/members", status_code=303)


@app.post("/members/{account_id}/rename")
def members_rename(account_id: str, display_name: str = Form(...)):
    get_member_roster_service().rename_member(account_id, display_name.strip())
    return RedirectResponse(url="/members", status_code=303)


@app.post("/members/{account_id}/delete")
def members_delete(account_id: str):
    get_member_roster_service().remove_member(account_id)
    return RedirectResponse(url="/members", status_code=303)


@app.get("/risk", response_class=HTMLResponse)
def risk(
    request: Request,
    stale_days: int = Query(DEFAULT_STALL_THRESHOLD_DAYS, ge=1, le=_MAX_WINDOW_DAYS),
):
    """Scans only the member roster's own open issues — not every issue in
    whatever projects they happen to touch. "無人認領" will always come up
    empty here (an unassigned issue can't belong to a tracked member); that's
    the correct, honest result of scoping to people rather than projects,
    not a bug.
    """
    context = {"stale_days": stale_days, "active_nav": "risk", "member_names": []}
    try:
        members = get_member_roster_service().list_members()
        context["member_names"] = [person.display_name for person in members]
        workload_reports = get_workload_report_service().build_reports_for_people(members)
        issues = [issue for report in workload_reports for issue in report.issues]
        scanner = TeamRiskScanner(stale_finder=StaleIssueFinder(threshold_days=stale_days))
        report = scanner.scan(issues, as_of=datetime.now(timezone.utc))
        context["report"] = team_risk_view(report)
    except _KNOWN_ERRORS as error:
        context["error"] = str(error)
    return templates.TemplateResponse(request, "risk.html", context)


@app.get("/audit", response_class=HTMLResponse)
def audit(
    request: Request,
    window_days: int = Query(_AUDIT_DEFAULT_WINDOW_DAYS, ge=1, le=_MAX_WINDOW_DAYS),
    stale_days: int = Query(DEFAULT_STALL_THRESHOLD_DAYS, ge=1, le=_MAX_WINDOW_DAYS),
    group_by: str = Query("none"),
):
    """Everything the audited projects took in over the window, ranked by
    urgency. Which projects those are is configuration
    (AUDIT_PROJECT_KEYS) — unset, the page explains itself instead of
    guessing at a key that may not exist on this Jira site.

    Scoped by *project*, unlike /risk which is scoped by people — so
    unlike there, "無人認領" here is a real category with real rows in it.
    """
    project_keys = audit_project_keys_from_env()
    context = {
        "active_nav": "audit",
        "window_days": window_days,
        "stale_days": stale_days,
        "group_by": normalize_group_by(group_by),
        "window_choices": _AUDIT_WINDOW_CHOICES,
        "group_by_options": audit_group_by_options(),
        "project_label": "/".join(project_keys),
    }
    if not project_keys:
        context["error"] = (
            "尚未設定要盤查的專案。請在 .env 加上 AUDIT_PROJECT_KEYS=你的專案代號"
            "(多個用逗號分隔,例如 AUDIT_PROJECT_KEYS=ABC,DEF)。"
        )
        return templates.TemplateResponse(request, "audit.html", context)
    try:
        # Same reason as /members: building the service reaches for Jira
        # configuration, so it has to sit inside the try.
        report = get_project_audit_service().build_report(
            project_keys,
            window_days=window_days,
            as_of=datetime.now(timezone.utc),
            stale_days=stale_days,
        )
        context["audit"] = project_audit_view(report, group_by)
    except _KNOWN_ERRORS as error:
        context["error"] = str(error)
    return templates.TemplateResponse(request, "audit.html", context)


@app.get("/weekly", response_class=HTMLResponse)
def weekly(
    request: Request,
    name: Optional[str] = None,
    account_id: Optional[str] = None,
    window_days: int = Query(DEFAULT_WEEKLY_WINDOW_DAYS, ge=1, le=_MAX_WINDOW_DAYS),
):
    context = {
        "name": name or "",
        "account_id": account_id or "",
        "window_days": window_days,
        "active_nav": "weekly",
        "members": [],
    }
    try:
        # Same reason as /members: the roster lookup itself can raise a
        # configuration error, so it has to sit inside the try.
        context["members"] = member_options_view(get_member_roster_service().list_members())
        person = _resolve_member(account_id)
        service = get_weekly_report_service()
        as_of = datetime.now(timezone.utc)
        if person is not None:
            report = service.build_report_for_person(person, as_of=as_of, window_days=window_days)
            context["report"] = weekly_view(report)
        elif name:
            report = service.build_report(name.strip(), as_of=as_of, window_days=window_days)
            context["report"] = weekly_view(report)
    except _KNOWN_ERRORS as error:
        context["error"] = str(error)
    return templates.TemplateResponse(request, "weekly.html", context)


def _parse_date(raw: str) -> Optional[date]:
    """`<input type="date">` submits either "" or YYYY-MM-DD.

    Anything else came from a hand-built POST, and dropping the field
    beats a 500 on a page whose handlers are otherwise total — same
    spirit as the mapper defaulting an unknown status category to todo.
    """
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


def _parse_tracking_status(raw: str) -> TrackingStatus:
    try:
        return TrackingStatus(raw.strip())
    except ValueError:
        return TrackingStatus.TODO


def _parse_tracking_priority(raw: str) -> TrackingPriority:
    try:
        return TrackingPriority(raw.strip())
    except ValueError:
        return TrackingPriority.MEDIUM


def _optional(raw: str) -> Optional[str]:
    return raw.strip() or None


def _tracking_now() -> datetime:
    """Local-aware, not UTC — unlike every other clock reading here.

    The other `as_of` values only ever feed interval arithmetic, but a
    tracking item's updated_at is *displayed*, and a UTC value renders as
    Taipei-minus-eight-hours. Staying tz-aware keeps isoformat round-trips
    intact.
    """
    return datetime.now().astimezone()


def _tracking_redirect() -> RedirectResponse:
    return RedirectResponse(url="/tracking", status_code=303)


@app.get("/tracking", response_class=HTMLResponse)
def tracking(request: Request):
    """The one page that needs no Jira configuration at all.

    The 負責人 datalist reads the roster straight from its local JSON
    store rather than through MemberRosterService, whose construction
    reaches for JiraConfig — going through the service would hand this
    page back the very dependency it exists without.
    """
    context = {
        "active_nav": "tracking",
        "members": [],
        "status_options": tracking_status_options(),
        "priority_options": tracking_priority_options(),
        "tracking": None,
    }
    try:
        # The follow-up list itself is read first: it is the reason this
        # page exists, and the roster is only needed to put a name on the
        # 個人工作量 routing.
        items = get_tracking_list_service().list_items()
        members = sorted(get_member_repository().list_members(), key=lambda p: p.display_name)
        context["members"] = member_options_view(members)
        context["tracking"] = tracking_view(
            items, member_names={person.account_id: person.display_name for person in members}
        )
    except _KNOWN_ERRORS as error:
        context["error"] = str(error)
    return templates.TemplateResponse(request, "tracking.html", context)


@app.post("/tracking/add")
def tracking_add(
    item: str = Form(...),
    status: str = Form(TrackingStatus.TODO.value),
    priority: str = Form(TrackingPriority.MEDIUM.value),
    due_date: str = Form(""),
    owner: str = Form(""),
    member_account_id: str = Form(""),
    link: str = Form(""),
    note: str = Form(""),
):
    # Like members_*, these handlers carry no try/except — every input path
    # is total instead: a blank description short-circuits here, unknown
    # enum values and malformed dates fall back, and an unknown id is a
    # no-op in the service.
    if not item.strip():
        return _tracking_redirect()
    get_tracking_list_service().add(
        item=item,
        now=_tracking_now(),
        status=_parse_tracking_status(status),
        priority=_parse_tracking_priority(priority),
        due_date=_parse_date(due_date),
        owner=_optional(owner),
        member_account_id=_optional(member_account_id),
        link=_optional(link),
        note=_optional(note),
    )
    return _tracking_redirect()


@app.post("/tracking/{item_id}/update")
def tracking_update(
    item_id: str,
    item: str = Form(...),
    status: str = Form(...),
    priority: str = Form(...),
    due_date: str = Form(""),
    owner: str = Form(""),
    member_account_id: str = Form(""),
    link: str = Form(""),
    note: str = Form(""),
):
    if not item.strip():
        return _tracking_redirect()
    get_tracking_list_service().update(
        item_id,
        now=_tracking_now(),
        item=item,
        status=_parse_tracking_status(status),
        priority=_parse_tracking_priority(priority),
        due_date=_parse_date(due_date),
        owner=_optional(owner),
        member_account_id=_optional(member_account_id),
        link=_optional(link),
        note=_optional(note),
    )
    return _tracking_redirect()


@app.post("/tracking/{item_id}/status")
def tracking_set_status(item_id: str, status: str = Form(...)):
    get_tracking_list_service().set_status(
        item_id, _parse_tracking_status(status), now=_tracking_now()
    )
    return _tracking_redirect()


@app.post("/tracking/{item_id}/delete")
def tracking_delete(item_id: str):
    get_tracking_list_service().delete(item_id)
    return _tracking_redirect()
