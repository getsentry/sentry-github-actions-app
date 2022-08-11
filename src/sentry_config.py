from __future__ import annotations

import base64
from configparser import ConfigParser
from functools import lru_cache

import requests

SENTRY_CONFIG_API_URL = (
    "https://api.github.com/repos/{owner}/.sentry/contents/sentry_config.ini"
)


def fetch_dsn_for_github_org(org: str, token: str) -> str:
    # Using the GH app token allows fetching the file in a private repo
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {token}",
    }
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
