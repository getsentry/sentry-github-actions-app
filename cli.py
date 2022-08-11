from __future__ import annotations

import json
import logging
import os
import sys

import requests

from src.github_app import GithubAppToken
from src.github_sdk import GithubClient
from src.sentry_config import fetch_dsn_for_github_org
from src.web_app_handler import init_config

logging.getLogger().setLevel(os.environ.get("LOGGING_LEVEL", "INFO"))
logging.basicConfig()

# Point this script to the URL of a job and we will trace it
# You give us this https://github.com/getsentry/sentry/runs/5759197422?check_suite_focus=true
# Or give it a path to a file with a webhook payload
# e.g. tests/fixtures/jobA/job.json


def main():
    url = sys.argv[1]
    token = None

    _, _, _, org, repo, _, run_id = url.split("?")[0].split("/")
    req = requests.get(
        f"https://api.github.com/repos/{org}/{repo}/actions/jobs/{run_id}",
    )
    req.raise_for_status()
    job = req.json()

    config = init_config()
    # When you install an APP under your org, the installation ID will be part of the url
    # e.g. https://github.com/settings/installations/<foo>
    # Visit https://github.com/settings/installations to find it
    installation_id = os.environ["INSTALLATION_ID"]
    with GithubAppToken(**config.gh_app._asdict()).get_token(installation_id) as token:
        # Once the Sentry org has a .sentry repo we can remove the DSN from the deployment
        dsn = fetch_dsn_for_github_org(org, token)
        client = GithubClient(
            token=token,
            dsn=dsn,
        )
        client.send_trace(job)


if __name__ == "__main__":
    raise SystemExit(main())
