"""Route-level tests for the FastAPI adapter.

The rest of tests/web/ covers the presenters in isolation; these exercise
the request handlers themselves, which is where error handling and query
validation actually live. Every service getter is monkeypatched, so no
Jira credentials or network access are involved.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from datetime import date, datetime, timedelta, timezone

from work_radar.application.workload_report import WorkloadReport
from work_radar.domain.exceptions import PersonNotFoundError
from work_radar.domain.models import Person, TrackingItem, TrackingPriority, TrackingStatus
from work_radar.infrastructure.config import ConfigurationError
from work_radar.web import app as web_app

_SERVICE_GETTERS = (
    "get_epic_report_service",
    "get_issue_comment_service",
    "get_member_repository",
    "get_member_roster_service",
    "get_overview_issue_note_repository",
    "get_overview_note_repository",
    "get_project_audit_service",
    "get_tracking_list_service",
    "get_weekly_report_service",
    "get_workload_report_service",
)

_PAGES = (
    "/",
    "/epic?key=GHI-1",
    "/workload",
    "/members?q=alice",
    "/weekly?name=alice",
    "/risk",
    "/audit",
    "/tracking",
)


@pytest.fixture
def client():
    return TestClient(web_app.app)


class FakeIssueNotes:
    """In-memory stand-in for the per-ticket note store. Patched in for
    every test so none of them reads or writes the real data/ directory.
    """

    def __init__(self, notes=None):
        self.notes = dict(notes or {})

    def read_all(self):
        return dict(self.notes)

    def update(self, notes):
        for key, note in notes.items():
            if note.strip():
                self.notes[key] = note
            else:
                self.notes.pop(key, None)


@pytest.fixture(autouse=True)
def issue_notes(monkeypatch):
    fake = FakeIssueNotes()
    monkeypatch.setattr(web_app, "get_overview_issue_note_repository", lambda: fake)
    return fake


@pytest.fixture
def unconfigured(monkeypatch):
    """Every dependency raises as if .env were missing or incomplete."""

    def _raise():
        raise ConfigurationError("Missing required environment variable(s): JIRA_EMAIL")

    for name in _SERVICE_GETTERS:
        monkeypatch.setattr(web_app, name, _raise)


@pytest.mark.parametrize("path", _PAGES)
def test_pages_render_an_error_banner_when_configuration_is_missing(client, unconfigured, path):
    """No page may 500 just because Jira credentials aren't set.

    /members and /weekly used to build their roster service outside the
    try block, so a missing .env produced a raw traceback there while
    every other page showed the banner.
    """
    response = client.get(path)

    assert response.status_code == 200
    if path != "/":  # the index page makes no service calls at all
        assert "JIRA_EMAIL" in response.text


@pytest.mark.parametrize(
    "path",
    [
        "/risk?stale_days=0",
        "/risk?stale_days=-5",
        "/weekly?window_days=0",
        "/weekly?window_days=-1",
        "/audit?window_days=0",
        "/audit?window_days=-30",
        "/audit?stale_days=0",
    ],
)
def test_nonsensical_windows_are_rejected(client, path):
    """`stale_days=0` marked every issue as stalled and a negative value
    built malformed JQL; both are now refused before any work happens.
    """
    assert client.get(path).status_code == 422


def test_weekly_reports_a_domain_error_as_a_banner(client, monkeypatch):
    class Roster:
        def list_members(self):
            return [Person(account_id="acc-1", display_name="Alice Wu")]

    class Weekly:
        def build_report(self, *args, **kwargs):
            raise PersonNotFoundError("nobody")

    monkeypatch.setattr(web_app, "get_member_roster_service", lambda: Roster())
    monkeypatch.setattr(web_app, "get_weekly_report_service", lambda: Weekly())

    response = client.get("/weekly?name=nobody")

    assert response.status_code == 200
    assert "nobody" in response.text
    # The roster dropdown still renders even though the query itself failed.
    assert "Alice Wu" in response.text


def test_workload_asks_for_work_completed_since_monday(client, monkeypatch, make_issue):
    """The page's "本週已完成" section is only as right as the window the
    route asks for, so pin the boundary it passes down.
    """
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    finished = make_issue(
        "ABC-1583",
        status_name="Done",
        completed_at=datetime(2026, 9, 10, 17, 3, tzinfo=timezone.utc),
    )
    asked_for = {}

    class Roster:
        def list_members(self):
            return [alice]

    class Workload:
        def build_reports_for_people(self, people, completed_since=None):
            asked_for["completed_since"] = completed_since
            return [WorkloadReport(person=alice, done_issues=[finished])]

    class Note:
        def read(self):
            return ""

    monkeypatch.setattr(web_app, "get_member_roster_service", lambda: Roster())
    monkeypatch.setattr(web_app, "get_workload_report_service", lambda: Workload())
    monkeypatch.setattr(web_app, "get_overview_note_repository", lambda: Note())

    response = client.get("/workload")

    today = date.today()
    assert asked_for["completed_since"] == today - timedelta(days=today.weekday())
    assert response.status_code == 200
    assert "本週已完成" in response.text
    assert "ABC-1583" in response.text


def test_backlog_flags_the_rows_that_already_carry_a_due_date(client, monkeypatch, make_issue):
    """Nothing in the backlog has been started, so a date on one of those
    rows is a commitment already running down — and a past date there is
    late without ever having been picked up.
    """
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    today = date.today()
    report = WorkloadReport(
        person=alice,
        issues=[
            make_issue("GHI-1", status_name="Pending", due_date=today - timedelta(days=3)),
            make_issue("GHI-2", status_name="Pending", due_date=today + timedelta(days=3)),
            make_issue("GHI-3", status_name="Pending", due_date=None),
        ],
    )

    class Roster:
        def list_members(self):
            return [alice]

    class Workload:
        def build_reports_for_people(self, people, completed_since=None):
            return [report]

    class Note:
        def read(self):
            return ""

    monkeypatch.setattr(web_app, "get_member_roster_service", lambda: Roster())
    monkeypatch.setattr(web_app, "get_workload_report_service", lambda: Workload())
    monkeypatch.setattr(web_app, "get_overview_note_repository", lambda: Note())

    body = client.get("/workload").text

    assert f'<td class="overdue-text">{(today - timedelta(days=3)).isoformat()}</td>' in body
    assert f'<td class="scheduled-text">{(today + timedelta(days=3)).isoformat()}</td>' in body
    # The undated majority stays unpainted, or the flag says nothing.
    assert '<td class="">—</td>' in body
    # The whole row is tinted, not just the date cell.
    assert '<tr class="row-overdue">' in body
    assert '<tr class="row-scheduled">' in body
    assert '<tr class="">' in body


@pytest.mark.parametrize(
    "path, expected",
    [
        ("/workload", True),
        ("/risk", True),
        ("/audit", True),
        ("/weekly", True),
        ("/epic", True),
        ("/members", True),
        # Nothing to re-fetch: a local JSON store, and a page with no calls.
        ("/tracking", False),
        ("/", False),
    ],
)
def test_refresh_button_appears_on_the_jira_backed_pages(client, unconfigured, path, expected):
    """Rendered even when Jira is unreachable — the banner those pages show
    is exactly the state you want a retry button for.
    """
    body = client.get(path).text

    assert ('class="refresh-tab"' in body) is expected


def test_workload_leads_with_the_unticketed_items_routed_to_that_member(client, monkeypatch):
    """A follow-up with no ticket yet is the one thing a Jira-derived
    report cannot know about, so it goes above the member's own tables.
    """
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    mine = _tracking_item(item="要 Carol 授權 FB 粉專", member_account_id="acc-1")
    someone_elses = _tracking_item(item="別人的事", member_account_id="acc-9")
    closed = _tracking_item(
        item="已經處理完的事", member_account_id="acc-1", status=TrackingStatus.DONE
    )

    class Roster:
        def list_members(self):
            return [alice]

    class Workload:
        def build_reports_for_people(self, people, completed_since=None):
            return [WorkloadReport(person=alice)]

    class Note:
        def read(self):
            return ""

    monkeypatch.setattr(web_app, "get_member_roster_service", lambda: Roster())
    monkeypatch.setattr(web_app, "get_workload_report_service", lambda: Workload())
    monkeypatch.setattr(web_app, "get_overview_note_repository", lambda: Note())
    monkeypatch.setattr(
        web_app,
        "get_tracking_list_service",
        lambda: FakeTrackingList([mine, someone_elses, closed]),
    )

    body = client.get("/workload").text

    assert "重要但尚未開票" in body
    assert "要 Carol 授權 FB 粉專" in body
    assert "別人的事" not in body
    assert "已經處理完的事" not in body


def test_workload_hides_the_unticketed_block_when_there_is_nothing_to_show(client, monkeypatch):
    alice = Person(account_id="acc-1", display_name="Alice Wu")

    class Roster:
        def list_members(self):
            return [alice]

    class Workload:
        def build_reports_for_people(self, people, completed_since=None):
            return [WorkloadReport(person=alice)]

    class Note:
        def read(self):
            return ""

    monkeypatch.setattr(web_app, "get_member_roster_service", lambda: Roster())
    monkeypatch.setattr(web_app, "get_workload_report_service", lambda: Workload())
    monkeypatch.setattr(web_app, "get_overview_note_repository", lambda: Note())
    monkeypatch.setattr(web_app, "get_tracking_list_service", lambda: FakeTrackingList([]))

    assert "重要但尚未開票" not in client.get("/workload").text


def test_tracking_page_shows_which_member_an_item_is_routed_to(client, monkeypatch):
    """Otherwise the routing is invisible until you open the edit form."""

    class Roster:
        def list_members(self):
            return [Person(account_id="acc-1", display_name="Alice Wu")]

    monkeypatch.setattr(
        web_app,
        "get_tracking_list_service",
        lambda: FakeTrackingList([_tracking_item(member_account_id="acc-1")]),
    )
    monkeypatch.setattr(web_app, "get_member_repository", lambda: Roster())

    body = client.get("/tracking").text

    assert "個人工作量:Alice Wu" in body
    # And the form offers the roster plus an opt-out.
    assert 'name="member_account_id"' in body
    assert "— 不顯示 —" in body


def test_audit_page_explains_itself_when_no_projects_are_configured(client, monkeypatch):
    """The first thing a fresh checkout hits: the project keys name one
    organisation's projects, so there is no sensible default and the page
    has to say what to set rather than build JQL from an empty list.
    """
    monkeypatch.delenv("AUDIT_PROJECT_KEYS", raising=False)

    response = client.get("/audit")

    assert response.status_code == 200
    assert "AUDIT_PROJECT_KEYS" in response.text


def test_comments_fragment_reports_its_own_failure_inline(client, monkeypatch):
    class Comments:
        def list_comments(self, key):
            raise ConfigurationError("no credentials")

    monkeypatch.setattr(web_app, "get_issue_comment_service", lambda: Comments())

    response = client.get("/issue/GHI-1/comments")

    assert response.status_code == 200
    assert "no credentials" in response.text


class FakeTrackingList:
    """Records what the routes hand the service, so the tests can assert on
    the parsing the adapter is responsible for.
    """

    def __init__(self, items=None):
        self.items = list(items or [])
        self.added = []
        self.updated = []
        self.statuses = []
        self.deleted = []

    def list_items(self):
        return list(self.items)

    def add(self, **kwargs):
        self.added.append(kwargs)

    def update(self, item_id, **kwargs):
        self.updated.append((item_id, kwargs))
        return None

    def set_status(self, item_id, status, *, now):
        self.statuses.append((item_id, status))
        return None

    def delete(self, item_id):
        self.deleted.append(item_id)


def _tracking_item(**overrides):
    now = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)
    fields = {"id": "id-1", "item": "跟法務確認 NDA", "created_at": now, "updated_at": now}
    fields.update(overrides)
    return TrackingItem(**fields)


def test_tracking_page_renders_without_any_jira_configuration(client, monkeypatch):
    """The whole point of the page: the store is local and the presenter
    never touches JiraConfig, so no credentials are involved.
    """

    class Roster:
        def list_members(self):
            return [Person(account_id="acc-1", display_name="Alice Wu")]

    monkeypatch.setattr(web_app, "get_tracking_list_service", lambda: FakeTrackingList([_tracking_item()]))
    monkeypatch.setattr(web_app, "get_member_repository", lambda: Roster())

    response = client.get("/tracking")

    assert response.status_code == 200
    assert "跟法務確認 NDA" in response.text
    # The roster only fills the owner datalist, and it came from the local
    # JSON store rather than a Jira lookup.
    assert "Alice Wu" in response.text
    assert "JIRA_EMAIL" not in response.text


def test_tracking_add_parses_the_form_into_domain_types(client, monkeypatch):
    service = FakeTrackingList()
    monkeypatch.setattr(web_app, "get_tracking_list_service", lambda: service)

    response = client.post(
        "/tracking/add",
        data={
            "item": "  跟進報價  ",
            "status": "waiting",
            "priority": "high",
            "due_date": "2026-09-20",
            "owner": "Alice Wu",
            "member_account_id": "acc-1",
            "link": "https://example.com",
            "note": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/tracking"
    (added,) = service.added
    assert added["status"] == TrackingStatus.WAITING
    assert added["priority"] == TrackingPriority.HIGH
    assert added["due_date"] == date(2026, 9, 20)
    assert added["owner"] == "Alice Wu"
    assert added["member_account_id"] == "acc-1"
    # A field left blank arrives as None, not "".
    assert added["note"] is None


def test_tracking_add_drops_nonsensical_form_values_instead_of_failing(client, monkeypatch):
    """Only a hand-built POST can produce these — `<input type="date">` and
    a `<select>` can't — and a dropped field beats a 500.
    """
    service = FakeTrackingList()
    monkeypatch.setattr(web_app, "get_tracking_list_service", lambda: service)

    response = client.post(
        "/tracking/add",
        data={"item": "x", "status": "wat", "priority": "urgent-ish", "due_date": "not-a-date"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    (added,) = service.added
    assert added["due_date"] is None
    assert added["status"] == TrackingStatus.TODO
    assert added["priority"] == TrackingPriority.MEDIUM
    # The blank "— 不顯示 —" option posts an empty string.
    assert added["member_account_id"] is None


def test_tracking_add_ignores_a_blank_description(client, monkeypatch):
    service = FakeTrackingList()
    monkeypatch.setattr(web_app, "get_tracking_list_service", lambda: service)

    response = client.post("/tracking/add", data={"item": "   "}, follow_redirects=False)

    assert response.status_code == 303
    assert service.added == []


def test_a_closed_item_offers_a_one_click_way_back_into_the_active_list(client, monkeypatch):
    """已完成 turning out not to be finished is a normal thing to happen,
    so the row posts status=todo instead of the 完成 it can't repeat.
    """

    class Roster:
        def list_members(self):
            return []

    service = FakeTrackingList([_tracking_item(status=TrackingStatus.DONE)])
    monkeypatch.setattr(web_app, "get_tracking_list_service", lambda: service)
    monkeypatch.setattr(web_app, "get_member_repository", lambda: Roster())

    page = client.get("/tracking")

    assert "重新追蹤" in page.text
    assert '<input type="hidden" name="status" value="todo">' in page.text

    client.post("/tracking/id-1/status", data={"status": "todo"}, follow_redirects=False)

    assert service.statuses == [("id-1", TrackingStatus.TODO)]


def test_tracking_update_forwards_a_typed_note_and_drops_a_blank_one(client, monkeypatch):
    """備註 is append-only, so the field posts empty on every edit that
    doesn't add to it — the blank has to reach the service as None.
    """
    service = FakeTrackingList()
    monkeypatch.setattr(web_app, "get_tracking_list_service", lambda: service)

    form = {"item": "跟法務確認 NDA", "status": "waiting", "priority": "high"}
    client.post("/tracking/id-1/update", data={**form, "note": "  還在等回覆  "}, follow_redirects=False)
    client.post("/tracking/id-1/update", data={**form, "note": "   "}, follow_redirects=False)

    assert [kwargs["note"] for _, kwargs in service.updated] == ["還在等回覆", None]


def test_tracking_mutations_on_an_unknown_id_redirect_rather_than_fail(client, monkeypatch):
    """A stale tab or a double-submitted form is a no-op, not an error."""
    service = FakeTrackingList()
    monkeypatch.setattr(web_app, "get_tracking_list_service", lambda: service)

    updated = client.post(
        "/tracking/nope/update",
        data={"item": "x", "status": "done", "priority": "low"},
        follow_redirects=False,
    )
    status = client.post("/tracking/nope/status", data={"status": "done"}, follow_redirects=False)
    deleted = client.post("/tracking/nope/delete", follow_redirects=False)

    assert [updated.status_code, status.status_code, deleted.status_code] == [303, 303, 303]
    assert service.statuses == [("nope", TrackingStatus.DONE)]
    assert service.deleted == ["nope"]


def _post_draft(client, content):
    return client.post("/workload/overview-draft", data={"content": content}, follow_redirects=False)


def test_saving_the_draft_stores_each_tickets_text_and_the_intro(client, monkeypatch, issue_notes, jira_domain):
    class Note:
        written = None

        def read(self):
            return ""

        def write(self, content):
            Note.written = content

    monkeypatch.setattr(web_app, "get_overview_note_repository", lambda: Note())

    response = _post_draft(
        client,
        "戰略方向\r\n\r\nOngoing Project\r\nAlice\r\n"
        f"- https://{jira_domain}/browse/ABC-1\r\n  - 優先權:高, 待PM驗完品質\r\n",
    )

    assert response.status_code == 303
    # Back to the page with the overview still open, not a collapsed panel.
    assert response.headers["location"] == "/workload?panel=overview"
    assert issue_notes.notes == {"ABC-1": "待PM驗完品質"}
    assert Note.written == "戰略方向"


def test_saving_a_draft_without_the_heading_leaves_the_intro_alone(client, monkeypatch, issue_notes, jira_domain):
    class Note:
        def write(self, content):
            raise AssertionError("intro must not be rewritten")

    monkeypatch.setattr(web_app, "get_overview_note_repository", lambda: Note())

    _post_draft(client, f"- https://{jira_domain}/browse/ABC-1\n  - 說明\n")

    assert issue_notes.notes == {"ABC-1": "說明"}


def test_workload_fills_the_draft_from_saved_notes_and_jira(client, monkeypatch, issue_notes, make_issue, jira_domain):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    issue = make_issue("ABC-1", status_name="Running", project_key="ABC", priority="High", assignee=alice)
    issue_notes.notes["ABC-1"] = "待PM驗完品質"

    class Roster:
        def list_members(self):
            return [alice]

    class Workload:
        def build_reports_for_people(self, people, completed_since=None):
            return [WorkloadReport(person=alice, issues=[issue])]

    class Note:
        def read(self):
            return ""

    monkeypatch.setattr(web_app, "get_member_roster_service", lambda: Roster())
    monkeypatch.setattr(web_app, "get_workload_report_service", lambda: Workload())
    monkeypatch.setattr(web_app, "get_overview_note_repository", lambda: Note())

    body = client.get("/workload?panel=overview").text

    assert "優先權:高, 待PM驗完品質" in body
    assert "1 張票帶入先前儲存的說明" in body
    panel_tag = body.split('<div id="overview-panel"', 1)[1].split(">", 1)[0]
    assert "hidden" not in panel_tag  # open


def test_members_page_toggles_the_overview_flag(client, monkeypatch):
    calls = []

    class Roster:
        def set_in_overview(self, account_id, included):
            calls.append((account_id, included))

    monkeypatch.setattr(web_app, "get_member_roster_service", lambda: Roster())

    response = client.post("/members/acc-1/overview", data={"include": "false"}, follow_redirects=False)

    assert response.status_code == 303
    assert calls == [("acc-1", False)]
