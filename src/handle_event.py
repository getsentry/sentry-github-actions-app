from http import client
import os
from .github_sdk import GithubClient

# We need an authorized token to fetch the API. If you have SSO on your org you will need to grant permission
# Your app and the Github webhook will share this secret
# You can create an .env file and place the token in it
GH_TOKEN = os.environ.get("GH_TOKEN")
# Where to report Github actions transactions
SENTRY_GITHUB_DSN = os.environ.get("SENTRY_GITHUB_DSN")

# XXX: Create a new function that does the try/finally of the main() function?
def handle_event(data, headers):
    # We return 200 to make webhook not turn red since everything got processed well
    http_code = 200
    reason = "OK"

    if headers["X-GitHub-Event"] != "workflow_job":
        reason = "Event not supported."
    elif data["action"] != "completed":
        reason = "We cannot do anything with this workflow state."
    else:
        client = GithubClient(
            dsn=SENTRY_GITHUB_DSN,
            token=GH_TOKEN,
        )
        client.send_trace(data["workflow_job"])

    return reason, http_code
