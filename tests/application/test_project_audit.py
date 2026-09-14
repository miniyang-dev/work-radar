"""Tests for the project audit's urgency scoring and gap detection.

The scoring exists precisely because Jira's priority field is nearly
constant on the projects this tool watches, so most of these assert on
*relative order* between signals rather than on absolute numbers — the
weights are meant to be tunable without rewriting the suite.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from work_radar.application.project_audit import (
    ProjectAuditService,
    score_issue,
    urgency_level,
)
from work_radar.domain.models import Person, StatusCategory

AS_OF = datetime(2026, 9, 9, tzinfo=timezone.utc)
FRESH = datetime(2026, 9, 8, tzinfo=timezone.utc)


class FakeIssues:
    def __init__(self, issues):
        self._issues = list(issues)
        self.calls = []

    def find_issues_created_since_for_projects(self, project_keys, window_days):
        self.calls.append((list(project_keys), window_days))
        return list(self._issues)


def _score(issue):
    return score_issue(issue, AS_OF).score


def test_overdue_outranks_even_a_fresh_p0(make_issue):
    """The whole point of the composite score: a ticket past its date is
    more urgent than a high-priority one nobody has missed a date on yet.
    """
    overdue = make_issue("ABC-1", priority="P3", due_date=date(2026, 9, 8), updated_at=FRESH)
    fresh_p0 = make_issue("ABC-2", priority="P0", updated_at=FRESH)

    assert _score(overdue) > _score(fresh_p0)


def test_longer_overdue_ranks_above_shorter_overdue(make_issue):
    older = make_issue("ABC-1", due_date=date(2026, 8, 1), updated_at=FRESH)
    newer = make_issue("ABC-2", due_date=date(2026, 9, 8), updated_at=FRESH)

    assert _score(older) > _score(newer)


def test_priority_outranks_staleness(make_issue):
    """Staleness is a real signal but a weak one — a P0 opened yesterday
    still matters more than a P2 nobody has touched in a month.
    """
    p0 = make_issue("ABC-1", priority="P0", updated_at=FRESH)
    stale_p2 = make_issue("ABC-2", priority="P2", updated_at=datetime(2026, 8, 9, tzinfo=timezone.utc))

    assert _score(p0) > _score(stale_p2)


def test_both_priority_schemes_are_ranked(make_issue):
    """This Jira instance has P0..P3 *and* stock Highest..Lowest, so a
    project on the other scheme mustn't score flat.
    """
    highest = make_issue("ABC-1", priority="Highest", updated_at=FRESH)
    low = make_issue("ABC-2", priority="Low", updated_at=FRESH)

    assert _score(highest) > _score(low)


def test_an_unknown_priority_scores_as_the_middle_not_as_harmless(make_issue):
    unknown = make_issue("ABC-1", priority="Wat", updated_at=FRESH)
    lowest = make_issue("ABC-2", priority="Lowest", updated_at=FRESH)

    assert _score(unknown) > _score(lowest)


def test_unassigned_adds_urgency_and_says_so(make_issue):
    entry = score_issue(make_issue("ABC-1", updated_at=FRESH), AS_OF)
    assigned = score_issue(
        make_issue("ABC-2", updated_at=FRESH, assignee=Person(account_id="a", display_name="Alice")),
        AS_OF,
    )

    assert entry.score > assigned.score
    assert "無人認領" in entry.reasons


def test_a_done_issue_never_scores(make_issue):
    """A delivered ticket that was late is not urgent — scoring it would
    let it outrank something still on fire.
    """
    done = make_issue(
        "ABC-1",
        status_name="Done",
        status_category=StatusCategory.DONE,
        priority="P0",
        due_date=date(2026, 1, 1),
        updated_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )

    assert score_issue(done, AS_OF).score == 0


def test_each_signal_alone_reads_at_the_level_it_should(make_issue):
    """The thresholds are calibrated against these four cases — a fresh P0
    reading as merely 中 would make the column useless on a project whose
    tickets are almost all P2.
    """
    # Assigned, so each case isolates the priority signal — leaving them
    # unassigned would add its own weight and bump every one a level.
    owner = Person(account_id="a", display_name="Alice")
    overdue = make_issue(
        "ABC-1", priority="P3", due_date=date(2026, 9, 8), updated_at=FRESH, assignee=owner
    )
    p0 = make_issue("ABC-2", priority="P0", updated_at=FRESH, assignee=owner)
    p1 = make_issue("ABC-3", priority="P1", updated_at=FRESH, assignee=owner)
    quiet_p2 = make_issue("ABC-4", priority="P2", updated_at=FRESH, assignee=owner)

    assert score_issue(overdue, AS_OF).level == "危急"
    assert score_issue(p0, AS_OF).level == "高"
    assert score_issue(p1, AS_OF).level == "中"
    assert score_issue(quiet_p2, AS_OF).level == "低"


def test_urgency_levels_step_down_with_the_score():
    assert urgency_level(100) == "危急"
    assert urgency_level(30) == "高"
    assert urgency_level(15) == "中"
    assert urgency_level(0) == "低"


def test_report_ranks_open_issues_and_sets_done_aside(make_issue):
    issues = [
        make_issue("ABC-1", priority="P2", updated_at=FRESH),
        make_issue("ABC-2", priority="P0", updated_at=FRESH),
        make_issue("ABC-3", status_name="Done", status_category=StatusCategory.DONE, updated_at=FRESH),
    ]
    service = ProjectAuditService(FakeIssues(issues))

    report = service.build_report(["ABC"], window_days=90, as_of=AS_OF)

    assert [entry.issue.key for entry in report.open_entries] == ["ABC-2", "ABC-1"]
    assert [issue.key for issue in report.done_issues] == ["ABC-3"]


def test_equal_scores_keep_a_stable_order(make_issue):
    """Most of a window scores identically, and a list that reshuffles on
    every refresh can't be read.
    """
    issues = [
        make_issue("ABC-9", priority="P2", updated_at=FRESH),
        make_issue("ABC-2", priority="P2", updated_at=FRESH),
    ]
    report = ProjectAuditService(FakeIssues(issues)).build_report(
        ["ABC"], window_days=90, as_of=AS_OF
    )

    assert [entry.issue.key for entry in report.open_entries] == ["ABC-2", "ABC-9"]


def test_gaps_only_cover_open_issues(make_issue):
    """A finished ticket with no due date is a non-event; flagging it
    would bury the ones that still need the field filled in.
    """
    issues = [
        make_issue("ABC-1", updated_at=FRESH),
        make_issue(
            "ABC-2",
            status_name="Done",
            status_category=StatusCategory.DONE,
            updated_at=FRESH,
        ),
        make_issue("ABC-3", updated_at=datetime(2026, 8, 1, tzinfo=timezone.utc), due_date=date(2026, 12, 1)),
    ]
    report = ProjectAuditService(FakeIssues(issues)).build_report(
        ["ABC"], window_days=90, as_of=AS_OF, stale_days=14
    )

    assert [issue.key for issue in report.gaps.no_due_date] == ["ABC-1"]
    assert [issue.key for issue in report.gaps.unassigned] == ["ABC-1", "ABC-3"]
    assert [issue.key for issue in report.gaps.stale] == ["ABC-3"]
    assert report.gaps.stale_days == 14
    # The page renders these as counts rather than tables, so the counts
    # are the part that has to stay right.
    assert report.stats.no_due_date_count == 1
    assert report.stats.unassigned_count == 2
    assert report.stats.stale_count == 1


def test_stats_count_the_window(make_issue):
    alice = Person(account_id="a", display_name="Alice")
    issues = [
        make_issue("ABC-1", priority="P0", updated_at=FRESH, assignee=alice, due_date=date(2026, 9, 1)),
        make_issue("ABC-2", priority="P2", updated_at=FRESH),
        make_issue(
            "ABC-3", status_name="Done", status_category=StatusCategory.DONE, updated_at=FRESH
        ),
        make_issue(
            "ABC-4", status_name="Done", status_category=StatusCategory.DONE, updated_at=FRESH
        ),
    ]
    stats = ProjectAuditService(FakeIssues(issues)).build_report(
        ["ABC"], window_days=90, as_of=AS_OF
    ).stats

    assert stats.total == 4
    assert stats.open_count == 2
    assert stats.done_count == 2
    assert stats.done_rate == 50
    assert stats.overdue_count == 1
    assert stats.high_priority_count == 1
    assert stats.unassigned_count == 1
    assert stats.no_due_date_count == 1
    assert stats.median_stale_days == 1


def test_the_service_passes_the_window_straight_through(make_issue):
    repository = FakeIssues([])

    ProjectAuditService(repository).build_report(["ABC"], window_days=180, as_of=AS_OF)

    assert repository.calls == [(["ABC"], 180)]
