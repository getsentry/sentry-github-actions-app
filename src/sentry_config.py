from configparser import ConfigParser

import requests

SENTRY_CONFIG_API_URL = (
    "https://api.github.com/repos/{owner}/.sentry/contents/sentry_config.ini"
)
SENTRY_CONFIG_RAW_URL = (
    "https://raw.githubusercontent.com/{owner}/.sentry/main/sentry_config.ini"
)


def fetch_dsn_for_github_org(org: str) -> str:
    cp = ConfigParser()
    api_url = SENTRY_CONFIG_API_URL.replace("{owner}", org)

    # - Get meta about sentry_config.ini file
    req = requests.get(api_url)
    req.raise_for_status()
    resp = req.json()

    # - Fetch raw contents of file
    download_url = resp["download_url"]
    req = requests.get(download_url)
    req.raise_for_status()
    file_contents = req.text

    # - Read ini file and assertions
    cp.read_string(file_contents)
    return cp.get("sentry-github-actions-app", "dsn")
