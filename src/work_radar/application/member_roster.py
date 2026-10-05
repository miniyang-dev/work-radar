"""Use case: manage work-radar's own curated roster of people to track.

Distinct from PersonResolver (a one-off Jira name search used by
workload/stale/weekly) — a roster member is added once, via a Jira lookup,
and from then on can be picked directly (by account_id) everywhere a name
would otherwise need to be typed and re-resolved.
"""
from __future__ import annotations

from dataclasses import replace

from work_radar.domain.exceptions import PersonNotFoundError
from work_radar.domain.models import Person
from work_radar.domain.ports import MemberRepository, PersonRepository


class MemberRosterService:
    def __init__(self, member_repository: MemberRepository, person_repository: PersonRepository) -> None:
        self._members = member_repository
        self._people = person_repository

    def list_members(self) -> list[Person]:
        return sorted(self._members.list_members(), key=lambda person: person.display_name)

    def get_member(self, account_id: str) -> Person:
        for person in self._members.list_members():
            if person.account_id == account_id:
                return person
        raise PersonNotFoundError(account_id)

    def search_candidates(self, name_query: str) -> list[Person]:
        """Jira users matching the query, minus anyone already on the roster."""
        existing_ids = {person.account_id for person in self._members.list_members()}
        return [person for person in self._people.find_by_name(name_query) if person.account_id not in existing_ids]

    def add_member(self, person: Person) -> None:
        self._members.add_member(person)

    def rename_member(self, account_id: str, display_name: str) -> None:
        person = self.get_member(account_id)
        self._members.add_member(replace(person, display_name=display_name))

    def set_in_overview(self, account_id: str, included: bool) -> None:
        person = self.get_member(account_id)
        self._members.add_member(replace(person, in_overview=included))

    def remove_member(self, account_id: str) -> None:
        self._members.remove_member(account_id)
