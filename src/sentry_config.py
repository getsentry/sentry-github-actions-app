import base64
from functools import lru_cache
from configparser import ConfigParser

import requests

CACHE = {}
SENTRY_CONFIG_API_URL = (
    "https://api.github.com/repos/{owner}/.sentry/contents/sentry_config.ini"
)

# Remember the last 1000 orgs
@lru_cache(maxsize=1000)
def _org_dsn(org):
    return CACHE[org]


def fetch_dsn_for_github_org(org: str, token: str) -> str:
    if CACHE.get(org):
        return _org_dsn(org)

    print(f"The org {org} is not in the cache.")
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
    dsn = cp.get("sentry-github-actions-app", "dsn")
    # Store in the cache
    CACHE[org] = dsn
    return dsn
