from __future__ import annotations

import base64
import hmac
import logging
import os
from typing import NamedTuple

from src.sentry_config import fetch_dsn_for_github_org

from .github_app import GithubAppToken
from .github_sdk import GithubClient

LOGGING_LEVEL = os.environ.get("LOGGING_LEVEL", logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)


class WebAppHandler:
    def __init__(self, dry_run=False):
        self.config = init_config()
        self.dry_run = dry_run

    def handle_event(self, data, headers):
        # We return 200 to make webhook not turn red since everything got processed well
        http_code = 200
        reason = "OK"

        if headers["X-GitHub-Event"] != "workflow_job":
            reason = "Event not supported."
        elif data["action"] != "completed":
            reason = "We cannot do anything with this workflow state."
        else:
            # For now, this simplifies testing
            if self.dry_run:
                return reason, http_code

            # We are executing in Github App mode
            if self.config.gh_app:
                with GithubAppToken(
                    **self.config.gh_app._asdict()
                ).get_token() as token:
                    # "url": "https://api.github.com/repos/getsentry/sentry/actions/workflows/1174556",
                    org = data["workflow_job"]["url"]
                    import pdb

                    pdb.set()
                    dsn = fetch_dsn_for_github_org(org)
                    client = GithubClient(
                        token=token,
                        dsn=dsn,
                        dry_run=self.dry_run,
                    )
                    client.send_trace(data["workflow_job"])
            else:
                client = GithubClient(
                    token=self.config.gh.token,
                    dsn=self.config.sentry.dsn,
                    dry_run=self.dry_run,
                )
                client.send_trace(data["workflow_job"])

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
    webhook_secret: str | None
    token: str | None


class Config(NamedTuple):
    gh_app: GithubAppConfig | None
    gh: GitHubConfig


def get_gh_app_private_key():
    private_key = None
    # K_SERVICE is a reserved variable for Google Cloud services
    if os.environ.get("K_SERVICE") and not os.environ.get("GH_APP_PRIVATE_KEY"):
        # XXX: Put in here since it currently affects test execution
        # ImportError: dlopen(/Users/armenzg/code/github-actions-app/.venv/lib/python3.10/site-packages/grpc/_cython/cygrpc.cpython-310-darwin.so, 0x0002): tried: '/Users/armenzg/code/github-actions-app/.venv/lib/python3.10/site-packages/grpc/_cython/cygrpc.cpython-310-darwin.so'
        # (mach-o file, but is an incompatible architecture (have 'x86_64', need 'arm64e'))
        from google.cloud import secretmanager

        gcp_client = secretmanager.SecretManagerServiceClient()
        uri = (
            f"projects/sentry-dev-tooling/secrets/SentryGithubAppPrivateKey/versions/1"
        )

        logger.info(f"Grabbing secret from {uri}")
        private_key = base64.b64decode(
            gcp_client.access_secret_version(name=uri).payload.data.decode("UTF-8")
        )
    else:
        # This block only applies for development since we are not executing on GCP
        private_key = base64.b64decode(os.environ["GH_APP_PRIVATE_KEY"])
    return private_key


def init_config():
    gh_app = None
    try:
        # This variable is the key to enabling Github App mode or not
        if os.environ.get("GH_APP_ID"):
            private_key = get_gh_app_private_key()
            gh_app = GithubAppConfig(
                app_id=os.environ["GH_APP_ID"],
                # Under your organization, under integrations you should see the app installed
                # The URL will contain the id of your installation
                installation_id=os.environ["GH_APP_INSTALLATION_ID"],
                private_key=private_key,
            )
    except Exception as e:
        logger.exception(e)
        logger.warning(
            "We have failed to load the private key, however, we will fallback to the PAT method."
        )

    return Config(
        gh_app,
        GitHubConfig(
            # This token is a PAT
            token=os.environ.get("GH_TOKEN"),
            webhook_secret=os.environ.get("GH_WEBHOOK_SECRET"),
        ),
    )
