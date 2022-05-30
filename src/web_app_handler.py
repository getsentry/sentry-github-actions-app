import base64
import hmac
import logging
import os

from google.cloud import secretmanager

from .github_sdk import GithubClient
from .github_app import GithubAppClient

LOGGING_LEVEL = os.environ.get("LOGGING_LEVEL", logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)


class WebAppHandler:
    def __init__(self, dry_run=False):
        self.config = init_config()
        self.gh_client = self.configure_client(dry_run)

    def configure_client(self, dry_run):
        if self.config.get("gh_app"):
            gh_client = GithubAppClient(**self.config["gh_app"])
            token = gh_client.get_token()
        else:
            token = self.config["gh"]["token"]

        return GithubClient(
            token=token,
            dsn=self.config["sentry"]["dsn"],
            dry_run=dry_run,
        )

    def handle_event(self, data, headers):
        # We return 200 to make webhook not turn red since everything got processed well
        http_code = 200
        reason = "OK"

        if headers["X-GitHub-Event"] != "workflow_job":
            reason = "Event not supported."
        elif data["action"] != "completed":
            reason = "We cannot do anything with this workflow state."
        else:
            self.gh_client.send_trace(data["workflow_job"])

        return reason, http_code

    def valid_signature(self, body, headers):
        if not self.config["gh"]["webhook_secret"]:
            return True
        else:
            signature = headers["X-Hub-Signature-256"].replace("sha256=", "")
            body_signature = hmac.new(
                self.config["gh"]["webhook_secret"].encode(),
                msg=body,
                digestmod="sha256",
            ).hexdigest()
            return hmac.compare_digest(body_signature, signature)


def init_config():
    config = {
        "gh": {
            "webhook_secret": os.environ.get("GH_WEBHOOK_SECRET"),
        },
        "sentry": {
            # Where to report Github actions transactions
            "dsn": os.environ.get("SENTRY_GITHUB_DSN")
        },
    }

    # This variable is the key to enabling Github App mode or not
    if os.environ.get("GH_APP_ID"):
        config["gh_app"] = {
            "app_id": os.environ["GH_APP_ID"],
            # Under your organization, under integrations you should see the app installed
            # The URL will contain the id of your installation
            "installation_id": os.environ["GH_APP_INSTALLATION_ID"],
        }

        # K_SERVICE is a reserved variable for Google Cloud services
        if os.environ.get("K_SERVICE"):
            gcp_client = secretmanager.SecretManagerServiceClient()
            uri = f"projects/sentry-dev-tooling/secrets/GithubAppPrivateKey/versions/1"

            logger.info(f"Grabbing secret from {uri}")
            config["gh_app"]["private_key"] = base64.b64decode(
                gcp_client.access_secret_version(name=uri).payload.data.decode("UTF-8")
            )
        else:
            # This block only applies for development since we are not executing on GCP
            config["gh_app"]["private_key"] = base64.b64decode(
                os.environ["GH_APP_PRIVATE_KEY"]
            )
    else:
        config["gh"]["token"] = os.environ["GH_TOKEN"]

    return config
