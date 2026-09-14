"""Shared helper for building a status name->category lookup across projects.

Used by any use case that needs to classify changelog transitions (which
carry only a status name) — currently cycle_time.py and weekly_report.py.
"""
from __future__ import annotations

from work_radar.domain.models import StatusCategory
from work_radar.domain.ports import StatusCatalogRepository


def merge_status_catalogs(
    project_keys: list[str],
    status_catalog_repository: StatusCatalogRepository,
) -> dict[str, StatusCategory]:
    catalog: dict[str, StatusCategory] = {}
    for project_key in project_keys:
        catalog.update(status_catalog_repository.get_status_catalog(project_key))
    return catalog
