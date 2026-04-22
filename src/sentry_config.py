from __future__ import annotations

import base64
import logging
import os
import time
from configparser import ConfigParser

import requests

LOGGING_LEVEL = os.environ.get("LOGGING_LEVEL", logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)

SENTRY_CONFIG_API_URL = (
    "https://api.github.com/repos/{owner}/.sentry/contents/sentry_config.ini"
)
GITHUB_API_TIMEOUT_SECONDS = float(os.environ.get("GITHUB_API_TIMEOUT_SECONDS", "10"))
GITHUB_API_MAX_RETRIES = int(os.environ.get("GITHUB_API_MAX_RETRIES", "2"))
GITHUB_API_RETRY_BACKOFF_SECONDS = float(
    os.environ.get("GITHUB_API_RETRY_BACKOFF_SECONDS", "0.5")
)


def _github_get_with_retries(url: str, headers: dict[str, str]) -> requests.Response:
    total_attempts = GITHUB_API_MAX_RETRIES + 1
    for attempt in range(1, total_attempts + 1):
        try:
            return requests.get(
                url,
                headers=headers,
                timeout=GITHUB_API_TIMEOUT_SECONDS,
            )
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            if attempt == total_attempts:
                raise
            wait_seconds = GITHUB_API_RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
            logger.warning(
                "GitHub API request failed; retrying in %.1fs (%s/%s)",
                wait_seconds,
                attempt + 1,
                total_attempts,
            )
            time.sleep(wait_seconds)


def fetch_dsn_for_github_org(org: str, token: str) -> str:
    # Using the GH app token allows fetching the file in a private repo
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {token}",
    }
    try:
        api_url = SENTRY_CONFIG_API_URL.replace("{owner}", org)

        # - Get meta about sentry_config.ini file
        resp = _github_get_with_retries(api_url, headers)
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
