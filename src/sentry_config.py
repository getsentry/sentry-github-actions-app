from __future__ import annotations

import base64
import logging
import os
import time
from configparser import ConfigParser
from functools import lru_cache

import requests
from requests import exceptions as requests_exceptions

LOGGING_LEVEL = os.environ.get("LOGGING_LEVEL", logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)

SENTRY_CONFIG_API_URL = (
    "https://api.github.com/repos/{owner}/.sentry/contents/sentry_config.ini"
)
GITHUB_API_TIMEOUT_SECONDS = float(os.environ.get("GITHUB_API_TIMEOUT_SECONDS", "10"))
MAX_GITHUB_API_ATTEMPTS = int(os.environ.get("MAX_GITHUB_API_ATTEMPTS", "3"))
GITHUB_API_RETRY_BACKOFF_SECONDS = float(
    os.environ.get("GITHUB_API_RETRY_BACKOFF_SECONDS", "1")
)


def fetch_dsn_for_github_org(org: str, token: str) -> str:
    # Using the GH app token allows fetching the file in a private repo
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {token}",
    }
    api_url = SENTRY_CONFIG_API_URL.replace("{owner}", org)

    for attempt in range(1, MAX_GITHUB_API_ATTEMPTS + 1):
        try:
            # - Get meta about sentry_config.ini file
            resp = requests.get(
                api_url,
                headers=headers,
                timeout=GITHUB_API_TIMEOUT_SECONDS,
            )
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
        except (requests_exceptions.ConnectionError, requests_exceptions.Timeout) as e:
            if attempt == MAX_GITHUB_API_ATTEMPTS:
                logger.exception(
                    "Failed to fetch sentry config from GitHub for org '%s' after %s attempts",
                    org,
                    MAX_GITHUB_API_ATTEMPTS,
                )
                raise e

            logger.warning(
                "Transient GitHub API failure while fetching sentry config for org '%s' (attempt %s/%s): %s",
                org,
                attempt,
                MAX_GITHUB_API_ATTEMPTS,
                type(e).__name__,
            )
            time.sleep(GITHUB_API_RETRY_BACKOFF_SECONDS * attempt)
        except Exception as e:
            logger.exception(e)
            raise e
