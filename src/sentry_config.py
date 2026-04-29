from __future__ import annotations

import base64
import logging
import os
from configparser import ConfigParser

import requests

LOGGING_LEVEL = os.environ.get("LOGGING_LEVEL", logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)

SENTRY_CONFIG_API_URL = (
    "https://api.github.com/repos/{owner}/.sentry/contents/sentry_config.ini"
)
GITHUB_API_TIMEOUT_SECONDS = 10
GITHUB_API_RETRIES = 2
GITHUB_API_RETRY_STATUS_CODES = {500, 502, 503, 504}


def _fetch_github_config(api_url: str, headers: dict[str, str]) -> requests.Response:
    for attempt in range(GITHUB_API_RETRIES + 1):
        try:
            resp = requests.get(
                api_url,
                headers=headers,
                timeout=GITHUB_API_TIMEOUT_SECONDS,
            )
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            if attempt == GITHUB_API_RETRIES:
                raise
            logger.warning("Retrying transient GitHub config fetch failure")
            continue

        if resp.status_code not in GITHUB_API_RETRY_STATUS_CODES:
            return resp
        if attempt == GITHUB_API_RETRIES:
            return resp
        logger.warning(
            "Retrying GitHub config fetch after HTTP %s",
            resp.status_code,
        )

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
        resp = _fetch_github_config(api_url, headers)
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
