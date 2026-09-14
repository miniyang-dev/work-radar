"""Shared logic for resolving a free-text name into exactly one Person.

Used by every use case that takes a "name query" from a human (workload,
weekly report, ...) so the ambiguous/not-found handling lives in one place.
"""
from __future__ import annotations

from work_radar.domain.exceptions import AmbiguousPersonError, PersonNotFoundError
from work_radar.domain.models import Person
from work_radar.domain.ports import PersonRepository


class PersonResolver:
    def __init__(self, person_repository: PersonRepository) -> None:
        self._people = person_repository

    def resolve(self, name_query: str) -> Person:
        matches = self._people.find_by_name(name_query)
        if not matches:
            raise PersonNotFoundError(name_query)
        if len(matches) > 1:
            raise AmbiguousPersonError(name_query, matches)
        return matches[0]
