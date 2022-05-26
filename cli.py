import json
import os
import sys

import requests

from src.github_sdk import GithubClient
from src.github_app import get_access_tokens


# Point this script to the URL of a job and we will trace it
# You give us this https://github.com/getsentry/sentry/runs/5759197422?check_suite_focus=true
# Or give it a path to a file with a webhook payload
# e.g. tests/fixtures/jobA/job.json
if __name__ == "__main__":
    argument = sys.argv[1]
    token = None

    if argument.startswith("https"):
        _, _, _, org, repo, _, run_id = argument.split("?")[0].split("/")
        req = requests.get(
            f"https://api.github.com/repos/{org}/{repo}/actions/jobs/{run_id}"
        )
        req.raise_for_status()
        job = req.json()
    else:
        with open(argument) as f:
            job = json.load(f)
        org = job["url"].split("/")[4]

    if os.environ.get("GH_APP_ID"):
        access_tokens = get_access_tokens()
        assert org in access_tokens, (
            f'You are trying to reach "{org}", however, '
            + f'we only have access to these orgs: "{access_tokens.keys()}".'
        )
        token = access_tokens[org]["token"]
    else:
        token = os.environ["GH_TOKEN"]

    client = GithubClient(
        token=token,
        dsn=os.environ.get("SENTRY_TEST_DSN"),
    )
    client.send_trace(job)
