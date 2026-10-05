"""Unit tests for MemberRosterService using in-memory fakes for both ports."""
from __future__ import annotations

import pytest

from work_radar.application.member_roster import MemberRosterService
from work_radar.domain.exceptions import PersonNotFoundError
from work_radar.domain.models import Person


class FakeMemberRepository:
    def __init__(self, members=None):
        self._members = list(members or [])

    def list_members(self):
        return list(self._members)

    def add_member(self, person):
        self._members = [m for m in self._members if m.account_id != person.account_id]
        self._members.append(person)

    def remove_member(self, account_id):
        self._members = [m for m in self._members if m.account_id != account_id]


class FakePersonRepository:
    def __init__(self, people):
        self._people = people

    def find_by_name(self, query):
        return [p for p in self._people if query.lower() in p.display_name.lower()]


def test_list_members_is_sorted_by_display_name():
    amy = Person(account_id="acc-2", display_name="Amy Lin")
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    # Stored out of alphabetical order, so the sort has something to do.
    service = MemberRosterService(FakeMemberRepository([amy, alice]), FakePersonRepository([]))

    assert [m.display_name for m in service.list_members()] == ["Alice Wu", "Amy Lin"]


def test_add_member_persists_to_the_repository():
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    repository = FakeMemberRepository()
    service = MemberRosterService(repository, FakePersonRepository([]))

    service.add_member(alice)

    assert repository.list_members() == [alice]


def test_get_member_returns_the_matching_person():
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    service = MemberRosterService(FakeMemberRepository([alice]), FakePersonRepository([]))

    assert service.get_member("acc-1") == alice


def test_get_member_raises_when_not_on_the_roster():
    service = MemberRosterService(FakeMemberRepository([]), FakePersonRepository([]))

    with pytest.raises(PersonNotFoundError):
        service.get_member("acc-404")


def test_rename_member_keeps_account_id_and_email():
    alice = Person(account_id="acc-1", display_name="Alice Wu", email="alice@example.com")
    repository = FakeMemberRepository([alice])
    service = MemberRosterService(repository, FakePersonRepository([]))

    service.rename_member("acc-1", "Alice W.")

    renamed = service.get_member("acc-1")
    assert renamed.display_name == "Alice W."
    assert renamed.account_id == "acc-1"
    assert renamed.email == "alice@example.com"


def test_remove_member_deletes_from_the_repository():
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    repository = FakeMemberRepository([alice])
    service = MemberRosterService(repository, FakePersonRepository([]))

    service.remove_member("acc-1")

    assert repository.list_members() == []


def test_search_candidates_excludes_people_already_on_the_roster():
    alice = Person(account_id="acc-1", display_name="Alice Wu")
    alice_lin = Person(account_id="acc-2", display_name="Alice Lin")
    service = MemberRosterService(FakeMemberRepository([alice]), FakePersonRepository([alice, alice_lin]))

    candidates = service.search_candidates("Alice")

    assert candidates == [alice_lin]


def test_set_in_overview_flips_only_the_flag():
    alice = Person(account_id="acc-1", display_name="Alice Wu", email="alice@example.com")
    repository = FakeMemberRepository([alice])
    service = MemberRosterService(repository, FakePersonRepository([]))

    service.set_in_overview("acc-1", False)

    assert service.get_member("acc-1") == Person(
        account_id="acc-1", display_name="Alice Wu", email="alice@example.com", in_overview=False
    )


def test_set_in_overview_for_an_unknown_member_raises():
    service = MemberRosterService(FakeMemberRepository([]), FakePersonRepository([]))

    with pytest.raises(PersonNotFoundError):
        service.set_in_overview("nope", False)


def test_renaming_a_member_keeps_their_overview_preference():
    repository = FakeMemberRepository([Person(account_id="acc-1", display_name="Alice Wu", in_overview=False)])
    service = MemberRosterService(repository, FakePersonRepository([]))

    service.rename_member("acc-1", "Alice W.")

    assert service.get_member("acc-1").in_overview is False
