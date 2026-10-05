"""Unit tests for JsonIssueNoteRepository, backed by a real file under tmp_path."""
from __future__ import annotations

from work_radar.infrastructure.storage.json_issue_note_repository import JsonIssueNoteRepository


def test_read_all_is_empty_when_the_file_does_not_exist(tmp_path):
    assert JsonIssueNoteRepository(tmp_path / "notes.json").read_all() == {}


def test_update_persists_across_instances_and_keeps_non_ascii_readable(tmp_path):
    path = tmp_path / "nested" / "notes.json"

    JsonIssueNoteRepository(path).update({"ABC-1": "待PM驗完品質"})

    assert JsonIssueNoteRepository(path).read_all() == {"ABC-1": "待PM驗完品質"}
    assert "待PM驗完品質" in path.read_text(encoding="utf-8")


def test_update_leaves_keys_it_was_not_given_untouched(tmp_path):
    repository = JsonIssueNoteRepository(tmp_path / "notes.json")
    repository.update({"ABC-1": "一", "ABC-2": "二"})

    repository.update({"ABC-2": "二改"})

    assert repository.read_all() == {"ABC-1": "一", "ABC-2": "二改"}


def test_a_blank_note_forgets_the_entry(tmp_path):
    repository = JsonIssueNoteRepository(tmp_path / "notes.json")
    repository.update({"ABC-1": "一", "ABC-2": "二"})

    repository.update({"ABC-1": "  ", "ABC-9": ""})

    assert repository.read_all() == {"ABC-2": "二"}
