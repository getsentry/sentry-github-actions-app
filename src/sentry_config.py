from __future__ import annotations

import base64
import logging
import os
import threading
from configparser import ConfigParser

import requests
from cachetools import cached
from cachetools import TTLCache
from cachetools.keys import hashkey

LOGGING_LEVEL = os.environ.get("LOGGING_LEVEL", logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)

SENTRY_CONFIG_API_URL = (
    "https://api.github.com/repos/{owner}/.sentry/contents/sentry_config.ini"
)
# Fetching the config on every webhook exhausts busy orgs' GitHub API rate limit
DSN_CACHE_TTL_SECONDS = 10 * 60


@cached(
    cache=TTLCache(maxsize=1024, ttl=DSN_CACHE_TTL_SECONDS),
    # The token is minted per webhook, so only the org identifies the DSN
    key=lambda org, token: hashkey(org),
    lock=threading.Lock(),
)
def fetch_dsn_for_github_org(org: str, token: str) -> str:
    # Using the GH app token allows fetching the file in a private repo
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {token}",
    }
    try:
        api_url = SENTRY_CONFIG_API_URL.replace("{owner}", org)

        # - Get meta about sentry_config.ini file
        resp = requests.get(api_url, headers=headers)
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
