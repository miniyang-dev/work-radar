"""Tests for the crash-safe file writer shared by the file-backed stores."""
from __future__ import annotations

import json

import pytest

from work_radar.domain.models import Person
from work_radar.infrastructure.storage.atomic_file import atomic_write_text
from work_radar.infrastructure.storage.json_member_repository import JsonMemberRepository


def test_creates_missing_parent_directories(tmp_path):
    target = tmp_path / "nested" / "deeper" / "note.txt"
    atomic_write_text(target, "hello")
    assert target.read_text(encoding="utf-8") == "hello"


def test_leaves_no_temp_files_behind(tmp_path):
    target = tmp_path / "note.txt"
    atomic_write_text(target, "first")
    atomic_write_text(target, "second")

    assert target.read_text(encoding="utf-8") == "second"
    assert [path.name for path in tmp_path.iterdir()] == ["note.txt"]


def test_a_failed_write_leaves_the_previous_content_intact(tmp_path, monkeypatch):
    """A plain write_text truncates first, so a crash mid-write left the
    roster file unreadable and every later read raising JSONDecodeError.
    """
    repository = JsonMemberRepository(tmp_path / "members.json")
    repository.add_member(Person(account_id="acc-1", display_name="Alice Wu"))

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("work_radar.infrastructure.storage.atomic_file.os.replace", boom)

    with pytest.raises(OSError):
        repository.add_member(Person(account_id="acc-2", display_name="Someone Else"))

    # Old content still parses, and the aborted write left no debris.
    assert [person.account_id for person in repository.list_members()] == ["acc-1"]
    assert json.loads((tmp_path / "members.json").read_text(encoding="utf-8"))
    assert [path.name for path in tmp_path.iterdir()] == ["members.json"]
