from __future__ import annotations

import base64
import logging
import os
import re
import threading
from configparser import ConfigParser
from typing import NamedTuple
from urllib.parse import quote

import requests
from cachetools import TTLCache

from src import REQUEST_TIMEOUT

LOGGING_LEVEL = os.environ.get("LOGGING_LEVEL", logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)

SENTRY_CONFIG_API_URL = (
    "https://api.github.com/repos/{owner}/.sentry/contents/sentry_config.ini"
)
# GitHub logins are up to 39 characters
GITHUB_OWNER_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
# Fetching the config on every webhook exhausts busy orgs' GitHub API rate limit
CONFIG_CACHE_TTL_SECONDS = 10 * 60
# Module globals rather than @cached, whose closure would put every cached DSN in the
# local variables Sentry captures with an error
_config_cache = TTLCache(maxsize=1024, ttl=CONFIG_CACHE_TTL_SECONDS)
_config_cache_lock = threading.Lock()


class OrgConfig(NamedTuple):
    dsn: str
    # Workflow files (e.g. `backend.yml`) that have to pass for a commit to be green.
    # Empty means every workflow run for the commit counts.
    commit_workflows: frozenset = frozenset()


def fetch_config_for_github_org(
    org: str, token: str, installation_id: int
) -> OrgConfig:
    # Only serve a config to the installation whose token could read it
    key = (installation_id, org)
    with _config_cache_lock:
        config = _config_cache.get(key)
    if config is None:
        config = _fetch_config(org, token)
        with _config_cache_lock:
            _config_cache[key] = config
    return config


def fetch_dsn_for_github_org(org: str, token: str, installation_id: int) -> str:
    return fetch_config_for_github_org(org, token, installation_id).dsn


def _fetch_config(org: str, token: str) -> OrgConfig:
    # Using the GH app token allows fetching the file in a private repo
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {token}",
    }
    try:
        if not GITHUB_OWNER_PATTERN.fullmatch(org):
            raise ValueError(f"Invalid GitHub organization/login: {org!r}")

        safe_org = quote(org, safe="")
        api_url = SENTRY_CONFIG_API_URL.replace("{owner}", safe_org)

        # - Get meta about sentry_config.ini file
        resp = requests.get(api_url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        meta = resp.json()

        if meta["type"] != "file":
            # XXX: custom error
            raise Exception(meta["type"])

        assert meta["encoding"] == "base64", meta["encoding"]
        file_contents = base64.b64decode(meta["content"]).decode()

        # - Read ini file and assertions
        cp = ConfigParser()
        cp.read_string(file_contents)
        section = "sentry-github-actions-app"
        # e.g. `commit_workflows = backend.yml, frontend.yml`
        commit_workflows = cp.get(section, "commit_workflows", fallback="")
        return OrgConfig(
            dsn=cp.get(section, "dsn"),
            commit_workflows=frozenset(
                w.strip()
                for w in commit_workflows.replace("\n", ",").split(",")
                if w.strip()
            ),
        )

    except Exception as e:
        logger.exception(e)
        raise e
