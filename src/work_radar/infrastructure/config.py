"""Environment-based configuration for the Jira adapter."""
from __future__ import annotations

import functools
import os
from dataclasses import dataclass
from pathlib import Path


class ConfigurationError(Exception):
    """Raised when required configuration is missing or invalid."""


def _project_root() -> Path:
    """The directory relative paths in configuration are anchored to.

    Defaults used to be resolved against the process's working directory,
    which meant starting uvicorn from anywhere but the repo root silently
    produced an *empty* roster and then wrote a brand-new file next to
    wherever it was launched — a data-loss-shaped surprise, not an error.

    When work-radar runs from a source checkout (the normal case, installed
    with `pip install -e .`) the repo root is derivable from this file's
    location; for a non-editable install there is no such root, so the
    working directory stays the fallback.
    """
    candidate = Path(__file__).resolve().parents[3]
    if (candidate / "pyproject.toml").exists():
        return candidate
    return Path.cwd()


def _resolve_path(env_var: str, default_relative: str) -> Path:
    """An explicit override is honoured as-is (absolute or cwd-relative);
    only the built-in default is anchored to the project root.
    """
    _load_dotenv()
    override = os.environ.get(env_var)
    if override:
        return Path(override)
    return _project_root() / default_relative


@dataclass(frozen=True)
class JiraConfig:
    email: str
    api_token: str
    domain: str

    @classmethod
    def from_env(cls, env_path: Path | None = None) -> "JiraConfig":
        _load_dotenv(env_path)

        values = {
            "email": os.environ.get("JIRA_EMAIL"),
            "api_token": os.environ.get("JIRA_API_TOKEN"),
            "domain": os.environ.get("JIRA_DOMAIN"),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            env_names = ", ".join(f"JIRA_{name.upper()}" for name in missing)
            raise ConfigurationError(f"Missing required environment variable(s): {env_names}")

        return cls(**values)


def member_store_path_from_env() -> Path:
    """Where the local member roster (JsonMemberRepository) is persisted.

    Defaults to `data/members.json` under the project root — overridable
    via MEMBER_STORE_PATH for tests or alternate deployments.
    """
    return _resolve_path("MEMBER_STORE_PATH", "data/members.json")


def overview_note_path_from_env() -> Path:
    """Where the workload page's saved "intro" note is persisted.

    Defaults to `data/overview_note.txt` under the project root —
    overridable via OVERVIEW_NOTE_PATH.
    """
    return _resolve_path("OVERVIEW_NOTE_PATH", "data/overview_note.txt")


def overview_issue_notes_path_from_env() -> Path:
    """Where the per-ticket status lines for the weekly overview are kept.

    Defaults to `data/overview_issue_notes.json` under the project root —
    overridable via OVERVIEW_ISSUE_NOTES_PATH.
    """
    return _resolve_path("OVERVIEW_ISSUE_NOTES_PATH", "data/overview_issue_notes.json")


def tracking_store_path_from_env() -> Path:
    """Where the hand-kept 追蹤事項 follow-up list is persisted.

    Defaults to `data/tracking_items.json` under the project root —
    overridable via TRACKING_STORE_PATH. Needs no Jira configuration at
    all: this is the one feature with no tracker behind it.
    """
    return _resolve_path("TRACKING_STORE_PATH", "data/tracking_items.json")


def _project_keys_from_env(env_var: str) -> list[str]:
    """Reads a comma-separated list of tracker project keys.

    Empty by default, and an empty list is a meaningful value rather than
    a misconfiguration: these keys name one particular organisation's
    projects, so the shipped default has to be "none" and each deployment
    names its own. Blank entries are dropped so "ABC,,DEF" and trailing
    commas behave.
    """
    # Like _resolve_path: every accessor has to prime the .env load itself,
    # or a setting that lives only in the file is silently read as unset.
    _load_dotenv()
    raw = os.environ.get(env_var, "")
    return [key.strip() for key in raw.split(",") if key.strip()]


def audit_project_keys_from_env() -> list[str]:
    """Which projects the 專案盤查 page audits (AUDIT_PROJECT_KEYS).

    Unset means the page has nothing to scan and says so, rather than
    guessing at a project key that may not exist on this Jira site.
    """
    return _project_keys_from_env("AUDIT_PROJECT_KEYS")


def overview_project_rank_from_env() -> dict[str, int]:
    """Business priority order for the weekly overview draft, highest
    first (OVERVIEW_PROJECT_RANK, e.g. "ABC,DEF,GHI").

    Not derivable from any tracker field — it's a judgement call about
    which project matters most this quarter — so it's configuration, not
    code. Anything unlisted sorts after, alphabetically among itself.
    """
    return {key: index for index, key in enumerate(_project_keys_from_env("OVERVIEW_PROJECT_RANK"))}


def _load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader.

    Avoids a hard dependency on python-dotenv for two lines of parsing.
    Existing environment variables always take precedence over the file.
    Reading is cached per path: every config accessor calls this, and the
    file's contents can't usefully change mid-process once loaded.
    """
    _load_dotenv_cached(path or _project_root() / ".env")


@functools.lru_cache(maxsize=None)
def _load_dotenv_cached(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())
