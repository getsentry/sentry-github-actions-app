from __future__ import annotations

import base64
import hmac
import logging
import os
from typing import NamedTuple

from google.cloud import secretmanager

from .github_sdk import GithubClient
from .github_app import GithubAppClient

LOGGING_LEVEL = os.environ.get("LOGGING_LEVEL", logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)


class WebAppHandler:
    def __init__(self, dry_run=False):
        self.config = init_config()
        self.gh_client = GithubClient(
            token=self.config.gh.token,
            dsn=self.config.sentry.dsn,
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
        if not self.config.gh.webhook_secret:
            return True
        else:
            signature = headers["X-Hub-Signature-256"].replace("sha256=", "")
            body_signature = hmac.new(
                self.config.gh.webhook_secret.encode(),
                msg=body,
                digestmod="sha256",
            ).hexdigest()
            return hmac.compare_digest(body_signature, signature)


class GithubAppConfig(NamedTuple):
    app_id: int
    installation_id: int
    private_key: str


class GitHubConfig(NamedTuple):
    gh_app: GithubAppConfig | None
    webhook_secret: str | None
    token: str | None


class SentryConfig(NamedTuple):
    dsn: str | None


class Config(NamedTuple):
    gh: GitHubConfig
    sentry: SentryConfig


def init_config():
    gh_app = None
    # This variable is the key to enabling Github App mode or not
    if os.environ.get("GH_APP_ID"):
        # K_SERVICE is a reserved variable for Google Cloud services
        if os.environ.get("K_SERVICE"):
            # Put in here since it affects test execution
            gcp_client = secretmanager.SecretManagerServiceClient()
            uri = f"projects/sentry-dev-tooling/secrets/GithubAppPrivateKey/versions/1"

            logger.info(f"Grabbing secret from {uri}")
            private_key = base64.b64decode(
                gcp_client.access_secret_version(name=uri).payload.data.decode("UTF-8")
            )
        else:
            # This block only applies for development since we are not executing on GCP
            private_key = base64.b64decode(os.environ["GH_APP_PRIVATE_KEY"])

        gh_app = {
            "app_id": os.environ["GH_APP_ID"],
            # Under your organization, under integrations you should see the app installed
            # The URL will contain the id of your installation
            "installation_id": os.environ["GH_APP_INSTALLATION_ID"],
            "private_key": private_key,
        }

    config = Config(
        GitHubConfig(
            gh_app=GithubAppConfig(**gh_app),
            token=os.environ.get("GH_TOKEN"),
            webhook_secret=os.environ.get("GH_WEBHOOK_SECRET"),
        ),
        SentryConfig(dsn=os.environ.get("SENTRY_GITHUB_DSN")),
    )

    return config
