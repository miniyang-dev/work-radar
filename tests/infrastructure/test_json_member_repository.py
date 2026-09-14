"""Unit tests for JsonMemberRepository, backed by a real file under tmp_path."""
from __future__ import annotations

from work_radar.domain.models import Person
from work_radar.infrastructure.storage.json_member_repository import JsonMemberRepository


def test_list_members_is_empty_when_the_file_does_not_exist(tmp_path):
    repository = JsonMemberRepository(tmp_path / "members.json")

    assert repository.list_members() == []


def test_add_member_persists_across_instances(tmp_path):
    path = tmp_path / "nested" / "members.json"
    alice = Person(account_id="acc-1", display_name="Alice Wu", email="alice@example.com")

    JsonMemberRepository(path).add_member(alice)

    assert JsonMemberRepository(path).list_members() == [alice]


def test_add_member_upserts_by_account_id(tmp_path):
    repository = JsonMemberRepository(tmp_path / "members.json")
    repository.add_member(Person(account_id="acc-1", display_name="Alice Wu"))
    repository.add_member(Person(account_id="acc-1", display_name="Alice W."))

    members = repository.list_members()

    assert len(members) == 1
    assert members[0].display_name == "Alice W."


def test_remove_member_deletes_only_the_matching_account(tmp_path):
    path = tmp_path / "members.json"
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    amy = Person(account_id="acc-2", display_name="Amy Lin")
    repository = JsonMemberRepository(path)
    repository.add_member(alice)
    repository.add_member(amy)

    repository.remove_member("acc-1")

    assert repository.list_members() == [amy]
