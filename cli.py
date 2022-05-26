import json
import os
import sys

import requests

from src.github_sdk import GithubClient
from src.github_app import get_jwt_token, get_private_key, get_org_for_token


# Point this script to the URL of a job and we will trace it
# You give us this https://github.com/getsentry/sentry/runs/5759197422?check_suite_focus=true
# Or give it a path to a file with a webhook payload
# e.g. tests/fixtures/jobA/job.json
if __name__ == "__main__":
    argument = sys.argv[1]
    # Currently testing the GH app approach
    token = get_jwt_token(get_private_key(file_path=os.environ["GH_PRIVATE_KEY_PATH"]))
    valid_org = get_org_for_token(token)

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

    assert (
        org == valid_org
    ), f'The token provided is useful for "{valid_org}" but you are trying to ingest a job for "{org}".'

    client = GithubClient(
        token=token,
        dsn=os.environ.get("SENTRY_TEST_DSN"),
        github_app=True,
    )
    client.send_trace(job)
