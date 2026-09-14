"""Unit tests for merge_status_catalogs — pure logic, no I/O."""
from __future__ import annotations

from work_radar.application.status_catalog import merge_status_catalogs
from work_radar.domain.models import StatusCategory


class FakeStatusCatalogRepository:
    def __init__(self, catalogs_by_project: dict) -> None:
        self._catalogs_by_project = catalogs_by_project

    def get_status_catalog(self, project_key: str) -> dict:
        return self._catalogs_by_project.get(project_key, {})


def test_merges_catalogs_across_multiple_projects():
    repository = FakeStatusCatalogRepository(
        {
            "GHI": {"Running": StatusCategory.IN_PROGRESS, "Done": StatusCategory.DONE},
            "ABC": {"Reviewing": StatusCategory.IN_PROGRESS, "Done": StatusCategory.DONE},
        }
    )

    catalog = merge_status_catalogs(["GHI", "ABC"], repository)

    assert catalog == {
        "Running": StatusCategory.IN_PROGRESS,
        "Reviewing": StatusCategory.IN_PROGRESS,
        "Done": StatusCategory.DONE,
    }


def test_empty_project_list_returns_empty_catalog():
    repository = FakeStatusCatalogRepository({})

    assert merge_status_catalogs([], repository) == {}
