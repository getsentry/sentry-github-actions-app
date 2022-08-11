from __future__ import annotations

import logging
import os

import requests

from src.github_app import GithubAppToken
from src.github_sdk import GithubClient
from src.sentry_config import fetch_dsn_for_github_org
from src.web_app_handler import WebAppHandler

# import argparse
# import json


logging.getLogger().setLevel(os.environ.get("LOGGING_LEVEL", "INFO"))
logging.basicConfig()

# Point this script to the URL of a job and we will trace it
# You give us this https://github.com/getsentry/sentry/runs/5759197422?check_suite_focus=true
# Only support GH app and URL modes
def _ingest_run(url):
    _, _, _, org, repo, _, run_id = url.split("?")[0].split("/")
    req = requests.get(
        f"https://api.github.com/repos/{org}/{repo}/actions/jobs/{run_id}",
    )
    req.raise_for_status()
    job = req.json()

    web_app = WebAppHandler()
    with GithubAppToken(**web_app.config.gh_app._asdict()).get_token() as token:
        client = GithubClient(
            token=token,
            dsn=os.environ.get("SENTRY_GITHUB_DSN"),
        )
        client.send_trace(job)


def _fetch_private_file(org):
    web_app = WebAppHandler()

    with GithubAppToken(**web_app.config.gh_app._asdict()).get_token() as token:
        print(token)
        fetch_dsn_for_github_org(org, token)


def main():
    # parser = argparse.ArgumentParser()
    _fetch_private_file("armenzg-dev")


if __name__ == "__main__":
    raise SystemExit(main())
