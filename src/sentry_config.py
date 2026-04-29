from __future__ import annotations

import base64
import logging
import os
import time
from configparser import ConfigParser
from functools import lru_cache

import requests

LOGGING_LEVEL = os.environ.get("LOGGING_LEVEL", logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)

SENTRY_CONFIG_API_URL = (
    "https://api.github.com/repos/{owner}/.sentry/contents/sentry_config.ini"
)
GITHUB_API_MAX_ATTEMPTS = 3
GITHUB_API_RETRY_BACKOFF_SECONDS = 0.5
GITHUB_API_TIMEOUT_SECONDS = 10


def _fetch_github_config_metadata(api_url: str, headers: dict[str, str]) -> requests.Response:
    for attempt in range(1, GITHUB_API_MAX_ATTEMPTS + 1):
        try:
            return requests.get(
                api_url,
                headers=headers,
                timeout=GITHUB_API_TIMEOUT_SECONDS,
            )
        except (requests.ConnectionError, requests.Timeout):
            if attempt == GITHUB_API_MAX_ATTEMPTS:
                raise

            logger.warning(
                "Transient failure fetching Sentry config from GitHub; retrying",
                exc_info=True,
            )
            time.sleep(GITHUB_API_RETRY_BACKOFF_SECONDS * attempt)

    raise RuntimeError("unreachable")


def fetch_dsn_for_github_org(org: str, token: str) -> str:
    # Using the GH app token allows fetching the file in a private repo
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {token}",
    }
    try:
        api_url = SENTRY_CONFIG_API_URL.replace("{owner}", org)

        # - Get meta about sentry_config.ini file
        resp = _fetch_github_config_metadata(api_url, headers)
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
        raise
