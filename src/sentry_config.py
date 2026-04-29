from __future__ import annotations

import base64
import logging
import os
from configparser import ConfigParser
from functools import lru_cache

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

LOGGING_LEVEL = os.environ.get("LOGGING_LEVEL", logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)

SENTRY_CONFIG_API_URL = (
    "https://api.github.com/repos/{owner}/.sentry/contents/sentry_config.ini"
)
GITHUB_API_TIMEOUT_SECONDS = 10
GITHUB_API_RETRIES = 2


@lru_cache(maxsize=1)
def _github_api_session() -> requests.Session:
    retry = Retry(
        total=GITHUB_API_RETRIES,
        connect=GITHUB_API_RETRIES,
        read=GITHUB_API_RETRIES,
        status=GITHUB_API_RETRIES,
        backoff_factor=0.25,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://api.github.com/", adapter)
    return session


def fetch_dsn_for_github_org(org: str, token: str) -> str:
    # Using the GH app token allows fetching the file in a private repo
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {token}",
    }
    try:
        api_url = SENTRY_CONFIG_API_URL.replace("{owner}", org)

        # - Get meta about sentry_config.ini file
        resp = _github_api_session().get(
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

    except Exception as e:
        logger.exception(e)
        raise e
