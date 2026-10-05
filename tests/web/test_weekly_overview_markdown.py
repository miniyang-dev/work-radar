"""Unit tests for weekly_overview_markdown — the "Ongoing Project" draft.

Uses the real presenters module, which builds issue URLs from the Jira
settings conftest pins for the whole suite — take the `jira_domain` fixture
rather than writing a host into an assertion.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from work_radar.application.workload_report import WorkloadReport
from work_radar.domain.models import Person
from work_radar.web.presenters import (
    parse_overview_edits,
    weekly_overview_markdown,
    weekly_overview_view,
)


def test_overview_skips_members_with_no_active_issues(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    report = WorkloadReport(person=alice, issues=[make_issue("GHI-1", status_name="Pending")])

    markdown = weekly_overview_markdown([report])

    assert "Alice Wu" not in markdown


def test_overview_groups_by_member_and_orders_by_project_then_due_date(make_issue):
    """Project order is conftest's OVERVIEW_PROJECT_RANK (ABC,DEF,GHI),
    not a constant in the code — it names real projects, so it moved to
    configuration.
    """
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    de_issue = make_issue("GHI-1", status_name="Running", project_key="GHI", due_date=date(2026, 9, 1))
    tse_issue = make_issue("ABC-1", status_name="Running", project_key="ABC", due_date=date(2026, 9, 10))
    trn_issue = make_issue("DEF-1", status_name="Running", project_key="DEF", due_date=date(2026, 9, 5))
    report = WorkloadReport(person=alice, issues=[de_issue, trn_issue, tse_issue])

    markdown = weekly_overview_markdown([report])

    tse_pos = markdown.index("ABC-1")
    trn_pos = markdown.index("DEF-1")
    de_pos = markdown.index("GHI-1")
    assert tse_pos < trn_pos < de_pos


def test_overview_orders_projects_of_the_same_rank_by_due_date(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    later = make_issue("ABC-1", status_name="Running", project_key="ABC", due_date=date(2026, 9, 20))
    sooner = make_issue("ABC-2", status_name="Running", project_key="ABC", due_date=date(2026, 9, 5))
    report = WorkloadReport(person=alice, issues=[later, sooner])

    markdown = weekly_overview_markdown([report])

    assert markdown.index("ABC-2") < markdown.index("ABC-1")


def test_overview_lists_each_ticket_as_a_link(make_issue, jira_domain):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    issue = make_issue("ABC-1", status_name="Running", project_key="ABC")

    markdown = weekly_overview_markdown([WorkloadReport(person=alice, issues=[issue])])

    assert f"- https://{jira_domain}/browse/ABC-1" in markdown
    assert "1. https://" not in markdown


def test_overview_header_is_immediately_followed_by_the_member_name(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    issue = make_issue("ABC-1", status_name="Running")
    report = WorkloadReport(person=alice, issues=[issue])

    markdown = weekly_overview_markdown([report])

    assert "Ongoing Project\nAlice Wu\n" in markdown


def test_overview_no_longer_prints_the_labor_and_done_date_line(make_issue):
    """人力 was created-to-due, which read 178 days for a long-lived ticket
    and a negative count for one due before it was filed; it was deleted
    by hand every week.
    """
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    issue = make_issue(
        "ABC-1",
        status_name="Running",
        created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        due_date=date(2026, 8, 11),
    )

    markdown = weekly_overview_markdown([WorkloadReport(person=alice, issues=[issue])])

    assert "人力" not in markdown
    assert "完成日" not in markdown


def test_overview_has_no_priority_order_suffix_in_the_header(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    issue = make_issue("ABC-1", status_name="Running")
    markdown = weekly_overview_markdown([WorkloadReport(person=alice, issues=[issue])])

    assert markdown.startswith("Ongoing Project\n")
    assert "以下順序為優先順序" not in markdown


def test_overview_ends_with_the_last_members_tickets(make_issue):
    """There is no sign-off line: the draft ends where the content does,
    and whoever sends it adds their own closing.
    """
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    issue = make_issue("ABC-1", status_name="Running")
    markdown = weekly_overview_markdown([WorkloadReport(person=alice, issues=[issue])])

    assert markdown.strip().endswith("/browse/ABC-1")


def test_overview_prepends_the_saved_intro_note_when_given(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    issue = make_issue("ABC-1", status_name="Running")
    report = WorkloadReport(person=alice, issues=[issue])

    markdown = weekly_overview_markdown([report], intro="本季重點方向：\n第一項、第二項")

    assert markdown.startswith("本季重點方向：\n第一項、第二項\n\nOngoing Project")


def test_overview_skips_intro_block_when_blank(make_issue):
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    issue = make_issue("ABC-1", status_name="Running")
    report = WorkloadReport(person=alice, issues=[issue])

    markdown = weekly_overview_markdown([report], intro="   ")

    assert markdown.startswith("Ongoing Project")


def _running(make_issue, key, **kwargs):
    return make_issue(key, status_name="Running", **kwargs)


def _report(make_issue, *issues, name="Alice Wu", **person_kwargs):
    person = Person(account_id=f"acc-{name}", display_name=name, **person_kwargs)
    return WorkloadReport(person=person, issues=list(issues))


def test_overview_status_line_carries_the_jira_priority(make_issue):
    report = _report(make_issue, _running(make_issue, "ABC-1", project_key="ABC", priority="High"))

    markdown = weekly_overview_markdown([report])

    assert "ABC-1\n  - 優先權:高\n" in markdown + "\n"


def test_overview_maps_both_priority_schemes_to_the_same_words(make_issue):
    """The tracked projects use P0..P3, the others Highest..Lowest."""
    cases = {"P0": "最高", "Highest": "最高", "P1": "高", "High": "高", "P2": "中", "Medium": "中", "P3": "低", "Lowest": "低"}
    for jira_name, shown in cases.items():
        report = _report(make_issue, _running(make_issue, "ABC-1", priority=jira_name))

        assert f"  - 優先權:{shown}" in weekly_overview_markdown([report]), jira_name


def test_overview_shows_an_unrecognised_priority_as_is(make_issue):
    report = _report(make_issue, _running(make_issue, "ABC-1", priority="Blocker"))

    assert "  - 優先權:Blocker" in weekly_overview_markdown([report])


def test_overview_has_no_status_line_for_a_ticket_without_priority_or_note(make_issue):
    report = _report(make_issue, _running(make_issue, "ABC-1", priority=None))

    markdown = weekly_overview_markdown([report])

    assert "  - " not in markdown


def test_overview_internal_label_replaces_the_priority(make_issue):
    issue = _running(make_issue, "ABC-1", priority="Medium", labels=("內部任務",))

    markdown = weekly_overview_markdown([_report(make_issue, issue)])

    assert "  - 內部任務\n" in markdown + "\n"
    assert "優先權" not in markdown


def test_overview_appends_the_saved_note_after_the_jira_part(make_issue):
    issue = _running(make_issue, "ABC-1", priority="High")

    markdown = weekly_overview_markdown([_report(make_issue, issue)], issue_notes={"ABC-1": "本週回報狀態"})

    assert "  - 優先權:高, 本週回報狀態" in markdown


def test_overview_saved_note_alone_when_jira_has_nothing_to_add(make_issue):
    issue = _running(make_issue, "ABC-1", priority=None)

    markdown = weekly_overview_markdown([_report(make_issue, issue)], issue_notes={"ABC-1": "待PM驗完品質"})

    assert "  - 待PM驗完品質" in markdown


def test_overview_keeps_extra_saved_lines_verbatim(make_issue):
    issue = _running(make_issue, "ABC-1", priority="High")
    note = "第一行\n    - 第二行"

    markdown = weekly_overview_markdown([_report(make_issue, issue)], issue_notes={"ABC-1": note})

    assert "  - 優先權:高, 第一行\n    - 第二行" in markdown


def test_overview_ignores_saved_notes_for_tickets_that_are_not_listed(make_issue):
    issue = _running(make_issue, "ABC-1")

    markdown = weekly_overview_markdown([_report(make_issue, issue)], issue_notes={"ABC-9": "舊票的說明"})

    assert "舊票的說明" not in markdown


def test_overview_orders_by_priority_within_a_project_before_due_date(make_issue):
    """P1 sorts ahead of P2 even though the P2 ticket is due sooner."""
    urgent = _running(make_issue, "ABC-1", project_key="ABC", priority="P1", due_date=None)
    routine = _running(make_issue, "ABC-2", project_key="ABC", priority="P2", due_date=date(2026, 9, 1))

    markdown = weekly_overview_markdown([_report(make_issue, routine, urgent)])

    assert markdown.index("ABC-1") < markdown.index("ABC-2")


def test_overview_project_rank_still_outranks_priority(make_issue):
    """A Medium ticket in a higher-ranked project comes before a Highest one
    in a lower-ranked project.
    """
    top_project = _running(make_issue, "ABC-1", project_key="ABC", priority="Medium")
    low_project = _running(make_issue, "GHI-1", project_key="GHI", priority="Highest")

    markdown = weekly_overview_markdown([_report(make_issue, low_project, top_project)])

    assert markdown.index("ABC-1") < markdown.index("GHI-1")


def test_overview_puts_internal_tasks_last_within_their_project(make_issue):
    internal = _running(make_issue, "ABC-1", project_key="ABC", priority="Highest", labels=("內部任務",))
    ordinary = _running(make_issue, "ABC-2", project_key="ABC", priority="Low")

    markdown = weekly_overview_markdown([_report(make_issue, internal, ordinary)])

    assert markdown.index("ABC-2") < markdown.index("ABC-1")


def test_overview_skips_members_who_opted_out(make_issue):
    shown = _report(make_issue, _running(make_issue, "ABC-1"), name="Alice Wu")
    hidden = _report(make_issue, _running(make_issue, "ABC-2"), name="Yang Li", in_overview=False)

    markdown = weekly_overview_markdown([shown, hidden])

    assert "Alice Wu" in markdown and "ABC-1" in markdown
    assert "Yang Li" not in markdown and "ABC-2" not in markdown


def test_overview_view_counts_how_many_lines_were_carried_over(make_issue):
    report = _report(make_issue, _running(make_issue, "ABC-1"), _running(make_issue, "ABC-2"))

    view = weekly_overview_view([report], issue_notes={"ABC-1": "沿用", "ABC-2": "  ", "ABC-9": "不在清單"})

    assert view["carried_count"] == 1


def test_parse_reads_back_each_tickets_text_without_the_jira_part(jira_domain):
    text = (
        "Ongoing Project\n"
        "Alice Wu\n"
        f"- https://{jira_domain}/browse/ABC-1\n"
        "  - 優先權:高, 觀察Queue處理速度\n"
        f"- https://{jira_domain}/browse/ABC-2\n"
        "  - 內部任務, 需於2026-10-09前完成\n"
        f"- https://{jira_domain}/browse/ABC-3\n"
        "  - 優先權:中\n"
        f"- https://{jira_domain}/browse/ABC-4\n"
    )

    edits = parse_overview_edits(text)

    assert edits.notes == {
        "ABC-1": "觀察Queue處理速度",
        "ABC-2": "需於2026-10-09前完成",
        "ABC-3": "",
        "ABC-4": "",
    }


def test_parse_accepts_other_bullet_styles_and_fullwidth_punctuation(jira_domain):
    text = f"Ongoing Project\n- https://{jira_domain}/browse/ABC-1\n   - 優先權：高，結論: 不需回補\n"

    assert parse_overview_edits(text).notes == {"ABC-1": "結論: 不需回補"}


def test_parse_keeps_extra_lines_under_a_ticket(jira_domain):
    text = (
        "Ongoing Project\n"
        f"- https://{jira_domain}/browse/ABC-1\n"
        "  - 優先權:高, 第一行\n"
        "    - 第二行\n"
        "\n"
        "Bob\n"
    )

    assert parse_overview_edits(text).notes == {"ABC-1": "第一行\n    - 第二行"}


def test_parse_splits_the_intro_off_at_the_heading(jira_domain):
    text = f"戰略方向:\nA\nB\n\nOngoing Project\nAlice\n- https://{jira_domain}/browse/ABC-1\n"

    assert parse_overview_edits(text).intro == "戰略方向:\nA\nB"


def test_parse_leaves_the_intro_alone_when_the_heading_was_deleted(jira_domain):
    edits = parse_overview_edits(f"- https://{jira_domain}/browse/ABC-1\n  - 說明\n")

    assert edits.intro is None
    assert edits.notes == {"ABC-1": "說明"}


def test_parse_handles_crlf_from_a_browser_form(jira_domain):
    text = f"Ongoing Project\r\n- https://{jira_domain}/browse/ABC-1\r\n  - 說明\r\n"

    assert parse_overview_edits(text).notes == {"ABC-1": "說明"}


def test_saved_text_survives_a_generate_edit_parse_round_trip(make_issue):
    """What a person sees, edits and saves must come back identically next
    week, with the Jira part refreshed rather than frozen.
    """
    last_week = _running(make_issue, "ABC-1", priority="High")
    first_draft = weekly_overview_markdown([_report(make_issue, last_week)], issue_notes={"ABC-1": "待PM驗完品質"})
    saved = parse_overview_edits(first_draft).notes

    this_week = _running(make_issue, "ABC-1", priority="Low")
    second_draft = weekly_overview_markdown([_report(make_issue, this_week)], issue_notes=saved)

    assert "  - 優先權:低, 待PM驗完品質" in second_draft
    assert "優先權:高" not in second_draft


def test_overview_leaves_out_tickets_already_in_review(make_issue):
    running = make_issue("ABC-1", status_name="Running / 執行中")
    reviewing = make_issue("ABC-2", status_name="Reviewing / 驗收")

    markdown = weekly_overview_markdown([_report(make_issue, running, reviewing)])

    assert "ABC-1" in markdown
    assert "ABC-2" not in markdown


def test_overview_skips_a_member_whose_only_tickets_are_in_review(make_issue):
    only_review = _report(make_issue, make_issue("ABC-1", status_name="Reviewing"), name="Roger Yeh")

    assert "Roger Yeh" not in weekly_overview_markdown([only_review])


def test_overview_view_does_not_count_review_tickets_as_carried_over(make_issue):
    report = _report(make_issue, make_issue("ABC-1", status_name="Reviewing"))

    assert weekly_overview_view([report], issue_notes={"ABC-1": "x"})["carried_count"] == 0
