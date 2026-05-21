from __future__ import annotations

import base64
import logging
import os
from configparser import ConfigParser
from functools import lru_cache

import requests

LOGGING_LEVEL = os.environ.get("LOGGING_LEVEL", logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)

SENTRY_CONFIG_API_URL = (
    "https://api.github.com/repos/{owner}/.sentry/contents/sentry_config.ini"
)
GITHUB_REQUEST_TIMEOUT = 5
GITHUB_REQUEST_ATTEMPTS = 3
GITHUB_RETRYABLE_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
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
        resp = _fetch_sentry_config(api_url, headers)
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


def _fetch_sentry_config(api_url, headers):
    for attempt in range(1, GITHUB_REQUEST_ATTEMPTS + 1):
        try:
            return requests.get(
                api_url,
                headers=headers,
                timeout=GITHUB_REQUEST_TIMEOUT,
            )
        except GITHUB_RETRYABLE_EXCEPTIONS as e:
            if attempt == GITHUB_REQUEST_ATTEMPTS:
                raise
            logger.warning(
                "Retrying GitHub Sentry config fetch after transient error: %s",
                e,
            )
