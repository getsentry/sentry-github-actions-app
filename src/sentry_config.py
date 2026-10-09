from __future__ import annotations

import base64
import logging
import os
import re
import threading
from configparser import ConfigParser
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
DSN_CACHE_TTL_SECONDS = 10 * 60
# Module globals rather than @cached, whose closure would put every cached DSN in the
# local variables Sentry captures with an error
_dsn_cache = TTLCache(maxsize=1024, ttl=DSN_CACHE_TTL_SECONDS)
_dsn_cache_lock = threading.Lock()


def fetch_dsn_for_github_org(org: str, token: str, installation_id: int) -> str:
    # Only serve a DSN to the installation whose token could read it
    key = (installation_id, org)
    with _dsn_cache_lock:
        dsn = _dsn_cache.get(key)
    if dsn is None:
        dsn = _fetch_dsn(org, token)
        with _dsn_cache_lock:
            _dsn_cache[key] = dsn
    return dsn


def _fetch_dsn(org: str, token: str) -> str:
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
        return cp.get("sentry-github-actions-app", "dsn")

    except Exception as e:
        logger.exception(e)
        raise e
