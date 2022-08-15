# This script only works if you have installed the GH app on an org OR you have created an app with the same permissions
#
# This script can be used to ingest a GH job. To ingest a job point it to the URL showing you the log of a job
# NOTE: Make sure "?check_suite_focus=true" is not included; zsh does not like it
# For instance https://github.com/getsentry/sentry/runs/5759197422?check_suite_focus=true
from __future__ import annotations

import argparse
import logging
import os

import requests

from src.github_app import GithubAppToken
from src.github_sdk import GithubClient
from src.sentry_config import fetch_dsn_for_github_org
from src.web_app_handler import WebAppHandler

logging.getLogger().setLevel(os.environ.get("LOGGING_LEVEL", "INFO"))
logging.basicConfig()


def _fetch_job(url: str) -> tuple(str, dict):
    _, _, _, org, repo, _, run_id = url.split("?")[0].split("/")
    req = requests.get(
        f"https://api.github.com/repos/{org}/{repo}/actions/jobs/{run_id}",
    )
    req.raise_for_status()
    job = req.json()
    return org, job


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--installation-id")
    args = parser.parse_args()

    org, job = _fetch_job(args.url)
    if org != "getsentry":
        assert (
            args.installation_id is not None
        ), "If you try to use a non-default org, you also need to specify the installation ID."

    # You can have a default installation ID by using an env variable
    installation_id = args.installation_id or os.environ["INSTALLATION_ID"]

    web_app = WebAppHandler()
    with GithubAppToken(**web_app.config.gh_app._asdict()).get_token(
        installation_id
    ) as token:
        dsn = fetch_dsn_for_github_org(org, token)
        client = GithubClient(token=token, dsn=dsn)
        client.send_trace(job)


if __name__ == "__main__":
    raise SystemExit(main())
