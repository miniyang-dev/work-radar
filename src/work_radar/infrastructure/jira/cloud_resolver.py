"""Resolves a Jira Cloud site's cloudId.

Required because API tokens created with explicit scopes must call
api.atlassian.com/ex/jira/{cloudId}/... rather than the site's own domain
directly. Isolated in its own class (single responsibility) so it can be
faked in tests without standing up an HTTP session.
"""
from __future__ import annotations

import requests

from work_radar.infrastructure.jira.errors import JiraApiError

_TENANT_INFO_TIMEOUT_SECONDS = 10


class CloudIdResolver:
    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    def resolve(self, domain: str) -> str:
        if domain not in self._cache:
            self._cache[domain] = self._fetch(domain)
        return self._cache[domain]

    @staticmethod
    def _fetch(domain: str) -> str:
        response = requests.get(
            f"https://{domain}/_edge/tenant_info",
            headers={"Accept": "application/json"},
            timeout=_TENANT_INFO_TIMEOUT_SECONDS,
        )
        if not response.ok:
            raise JiraApiError(
                response.status_code,
                f"Failed to resolve cloudId for {domain}: {response.text}",
            )
        return response.json()["cloudId"]
