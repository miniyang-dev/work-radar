"""JSON-file-backed MemberRepository.

work-radar's own curated roster of people, kept independent of whichever
issue tracker is plugged in via the other Protocols — no Jira calls here,
just a small local file survives process restarts.
"""
from __future__ import annotations

import json
import pathlib

from work_radar.domain.models import Person
from work_radar.infrastructure.storage.atomic_file import atomic_write_text


class JsonMemberRepository:
    def __init__(self, path: pathlib.Path) -> None:
        self._path = path

    def list_members(self) -> list[Person]:
        return self._read()

    def add_member(self, person: Person) -> None:
        members = [m for m in self._read() if m.account_id != person.account_id]
        members.append(person)
        self._write(members)

    def remove_member(self, account_id: str) -> None:
        members = [m for m in self._read() if m.account_id != account_id]
        self._write(members)

    def _read(self) -> list[Person]:
        if not self._path.exists():
            return []
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        return [
            Person(account_id=item["account_id"], display_name=item["display_name"], email=item.get("email"))
            for item in raw
        ]

    def _write(self, members: list[Person]) -> None:
        payload = [
            {"account_id": member.account_id, "display_name": member.display_name, "email": member.email}
            for member in members
        ]
        atomic_write_text(self._path, json.dumps(payload, ensure_ascii=False, indent=2))
