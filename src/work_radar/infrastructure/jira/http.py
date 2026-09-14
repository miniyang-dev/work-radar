"""Thin HTTP wrapper around the Jira Cloud REST API gateway.

Isolates every requests-specific detail (session, auth, base URL, error
translation) so repository adapters only ever talk in plain dicts.
"""
from __future__ import annotations

from typing import Any

import requests

from work_radar.infrastructure.config import JiraConfig
from work_radar.infrastructure.jira.cloud_resolver import CloudIdResolver
from work_radar.infrastructure.jira.errors import JiraApiError

_API_TIMEOUT_SECONDS = 15


class JiraHttpClient:
    def __init__(
        self,
        config: JiraConfig,
        cloud_id_resolver: CloudIdResolver | None = None,
    ) -> None:
        self._config = config
        self._cloud_id_resolver = cloud_id_resolver or CloudIdResolver()
        self._session = requests.Session()
        self._session.auth = (config.email, config.api_token)
        self._session.headers.update({"Accept": "application/json"})

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Returns the parsed JSON body — a dict for most endpoints, but a
        bare list for a few (e.g. /project/{key}/statuses).
        """
        url = f"{self._base_url()}{path}"
        response = self._session.get(url, params=params, timeout=_API_TIMEOUT_SECONDS)
        if not response.ok:
            raise JiraApiError(response.status_code, response.text)
        return response.json()

    def _base_url(self) -> str:
        cloud_id = self._cloud_id_resolver.resolve(self._config.domain)
        return f"https://api.atlassian.com/ex/jira/{cloud_id}"
