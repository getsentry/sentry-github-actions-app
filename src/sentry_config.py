from __future__ import annotations

import base64
import logging
import os
import re
from configparser import ConfigParser
from functools import lru_cache

import requests

LOGGING_LEVEL = os.environ.get("LOGGING_LEVEL", logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)

SENTRY_CONFIG_API_URL = (
    "https://api.github.com/repos/{owner}/.sentry/contents/sentry_config.ini"
)
GITHUB_API_TIMEOUT = (3.05, 10)
GITHUB_OWNER_RE = re.compile(r"^(?!-)[A-Za-z0-9-]{1,39}(?<!-)$")


def fetch_dsn_for_github_org(org: str, token: str) -> str:
    # Using the GH app token allows fetching the file in a private repo
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {token}",
    }
    try:
        if not isinstance(org, str) or not GITHUB_OWNER_RE.fullmatch(org):
            raise ValueError("Invalid GitHub organization/owner name.")

        safe_org = requests.utils.quote(org, safe="")
        api_url = SENTRY_CONFIG_API_URL.replace("{owner}", safe_org)

        # - Get meta about sentry_config.ini file
        resp = requests.get(api_url, headers=headers, timeout=GITHUB_API_TIMEOUT)
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
