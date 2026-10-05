"""Pure functions that translate raw Jira JSON into domain models.

Kept separate from the HTTP/repository code so the translation logic can
be unit tested without any network access.
"""
from __future__ import annotations

from datetime import date, datetime

from work_radar.domain.models import Comment, Issue, Person, Status, StatusCategory, StatusTransition

# Jira's own statusCategory keys, mapped onto our tracker-agnostic enum.
_CATEGORY_BY_KEY = {
    "new": StatusCategory.TODO,
    "indeterminate": StatusCategory.IN_PROGRESS,
    "done": StatusCategory.DONE,
}

# Jira renders timestamps as e.g. "2026-09-04T16:37:10.968+0800" — a UTC
# offset with no colon, which datetime.fromisoformat rejects on Python <3.11.
# Milliseconds are *usually* present but not guaranteed (some endpoints and
# older data omit them), so both shapes have to parse.
_JIRA_TIMESTAMP_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
)

# "Start date" is not a system field — it is a per-instance datepicker
# custom field, so its id is only valid for this Jira site (confirmed
# against /rest/api/3/field). Exported because the repository has to name
# it in the `fields` query parameter too.
START_DATE_FIELD = "customfield_10015"

# Jira stamps this on *every* status-category change, so on an open issue it
# holds the moment work started, not a completion time. Only read it for
# issues that are actually in the Done category.
STATUS_CATEGORY_CHANGED_FIELD = "statuscategorychangedate"


def to_status_category(category_key: str) -> StatusCategory:
    return _CATEGORY_BY_KEY.get(category_key, StatusCategory.TODO)


def to_status(raw: dict) -> Status:
    category_key = raw.get("statusCategory", {}).get("key", "new")
    return Status(name=raw["name"], category=to_status_category(category_key))


def to_person(raw: dict) -> Person:
    return Person(
        account_id=raw["accountId"],
        display_name=raw.get("displayName", raw["accountId"]),
        email=raw.get("emailAddress"),
    )


def _parse_timestamp(value: str) -> datetime:
    for timestamp_format in _JIRA_TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(value, timestamp_format)
        except ValueError:
            continue
    raise ValueError(f"Unrecognized Jira timestamp: {value!r}")


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _parse_completed_at(fields: dict, status: Status) -> datetime | None:
    changed_at = fields.get(STATUS_CATEGORY_CHANGED_FIELD)
    if status.category != StatusCategory.DONE or not changed_at:
        return None
    return _parse_timestamp(changed_at)


def to_issue(raw: dict) -> Issue:
    fields = raw["fields"]
    assignee_raw = fields.get("assignee")
    priority_raw = fields.get("priority")
    parent_raw = fields.get("parent")
    status = to_status(fields["status"])

    return Issue(
        key=raw["key"],
        summary=fields["summary"],
        status=status,
        project_key=fields["project"]["key"],
        issue_type=fields["issuetype"]["name"],
        updated_at=_parse_timestamp(fields["updated"]),
        created_at=_parse_timestamp(fields["created"]),
        assignee=to_person(assignee_raw) if assignee_raw else None,
        priority=priority_raw["name"] if priority_raw else None,
        parent_key=parent_raw["key"] if parent_raw else None,
        parent_summary=(parent_raw["fields"]["summary"] if parent_raw and "fields" in parent_raw else None),
        start_date=_parse_date(fields.get(START_DATE_FIELD)),
        due_date=_parse_date(fields.get("duedate")),
        completed_at=_parse_completed_at(fields, status),
        labels=tuple(fields.get("labels") or ()),
    )


def to_transitions(histories: list[dict]) -> list[StatusTransition]:
    """Extracts status-field changes from a list of changelog history entries.

    Takes the bare list rather than a wrapper dict because Jira uses two
    different shapes for the same data: bulk search's `expand=changelog`
    nests it under `changelog.histories`, while the dedicated
    `/issue/{key}/changelog` endpoint nests it under `values` — callers
    unwrap whichever shape they got before calling this.

    A single history entry can bundle edits to several fields (description,
    assignee, status, ...) under one timestamp — only "status" items matter
    here. Jira does not guarantee history order, so callers must sort by
    `occurred_at` themselves rather than trust the input order.
    """
    transitions: list[StatusTransition] = []
    for history in histories:
        occurred_at = _parse_timestamp(history["created"])
        for item in history.get("items", []):
            if item.get("field") == "status":
                transitions.append(
                    StatusTransition(
                        from_status=item.get("fromString"),
                        to_status=item["toString"],
                        occurred_at=occurred_at,
                    )
                )
    return transitions


_ADF_BLOCK_TYPES = ("paragraph", "heading", "listItem", "codeBlock", "blockquote")


def adf_to_plain_text(document: dict | None) -> str:
    """Flattens a Jira comment body (Atlassian Document Format) into plain
    text — good enough for a quick read, without writing a full ADF
    renderer. Marks (bold/italic/links) are dropped; mentions and emoji
    keep their display text.
    """
    if not document:
        return ""
    return _adf_node_to_text(document).strip()


def _adf_node_to_text(node: dict) -> str:
    node_type = node.get("type")
    if node_type == "text":
        return node.get("text", "")
    if node_type == "mention":
        return node.get("attrs", {}).get("text", "")
    if node_type == "emoji":
        attrs = node.get("attrs", {})
        return attrs.get("text") or attrs.get("shortName", "")
    if node_type == "hardBreak":
        return "\n"

    text = "".join(_adf_node_to_text(child) for child in node.get("content", []))
    return text + "\n" if node_type in _ADF_BLOCK_TYPES else text


def to_comment(raw: dict) -> Comment:
    author = raw.get("author", {}).get("displayName", "Unknown")
    return Comment(
        author=author,
        body=adf_to_plain_text(raw.get("body")),
        created_at=_parse_timestamp(raw["created"]),
    )


def to_comments(raw_comments: list[dict]) -> list[Comment]:
    return [to_comment(raw) for raw in raw_comments]


def to_status_catalog(raw_issue_types: list[dict]) -> dict[str, StatusCategory]:
    """Flattens a project's `/statuses` response (one status list per issue
    type, often overlapping) into a single name->category lookup.

    This is the only reliable source for classifying changelog transitions:
    a transition's `toString` is a status *name*, and the set of statuses
    actually observed on currently-fetched issues is never guaranteed to
    include every status the project's workflow has ever used (e.g. no
    currently-open issue happens to sit in "In Review" right now).
    """
    catalog: dict[str, StatusCategory] = {}
    for issue_type in raw_issue_types:
        for status in issue_type.get("statuses", []):
            catalog[status["name"]] = to_status_category(status["statusCategory"]["key"])
    return catalog
