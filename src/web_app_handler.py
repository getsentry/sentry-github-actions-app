from __future__ import annotations

import base64
import hmac
import logging
import os
from typing import NamedTuple

from sentry_sdk import metrics
from sentry_sdk.utils import BadDsn

from .github_app import GithubAppToken
from .github_sdk import GithubClient
from src.sentry_config import fetch_config_for_github_org

LOGGING_LEVEL = os.environ.get("LOGGING_LEVEL", logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)


def commit_traces_enabled() -> bool:
    # Off by default: it costs one GitHub API call per successful workflow run
    return os.environ.get("COMMIT_TRACES_ENABLED", "").lower() in ("1", "true")


class WebAppHandler:
    def __init__(self, dry_run=False):
        self.config = init_config()
        self.dry_run = dry_run

    def handle_event(self, data, headers):
        # We return 200 to make webhook not turn red since everything got processed well
        http_code = 200
        reason = "OK"
        event = headers["X-GitHub-Event"]

        if event == "workflow_job":
            if data["action"] != "completed":
                reason = "We cannot do anything with this workflow state."
            elif data["workflow_job"]["conclusion"] == "skipped":
                # These are not traced, so don't spend GitHub API calls on them
                reason = "Skipped jobs are not traced."
            elif not self.dry_run:
                reason = self._send(
                    data, lambda client, _: client.send_trace(data["workflow_job"])
                )
        elif event == "workflow_run":
            if not commit_traces_enabled():
                reason = "Commit traces are not enabled."
            elif data["action"] != "completed":
                reason = "We cannot do anything with this workflow state."
            elif data["workflow_run"]["conclusion"] != "success":
                # Only a successful run can turn its commit green, so don't spend
                # GitHub API calls on the others
                reason = "Only successful workflow runs can turn a commit green."
            elif not self.dry_run:
                reason = self._send(
                    data,
                    lambda client, config: client.send_commit_trace(
                        data["workflow_run"], config.commit_workflows
                    ),
                )
        else:
            reason = "Event not supported."

        return reason, http_code

    def _send(self, data, send) -> str:
        installation_id = data["installation"]["id"]
        org = data["repository"]["owner"]["login"]

        try:
            # We are executing in Github App mode
            if self.config.gh_app:
                with GithubAppToken(**self.config.gh_app._asdict()).get_token(
                    installation_id
                ) as token:
                    self._send_with_token(token, installation_id, org, send)
            else:
                self._send_with_token(self.config.gh.token, installation_id, org, send)
        except BadDsn as e:
            # It's up to the org to fix its .sentry repo, so this isn't an error on our end
            logger.warning("%s has an invalid DSN in its sentry_config.ini: %s", org, e)
            metrics.count("invalid_dsn", 1, attributes={"owner": org})
            return "The DSN in the org's .sentry/sentry_config.ini is invalid."
        return "OK"

    def _send_with_token(self, token, installation_id, org, send):
        # Once the Sentry org has a .sentry repo we can remove the DSN from the deployment
        config = fetch_config_for_github_org(org, token, installation_id)
        client = GithubClient(token=token, dsn=config.dsn, dry_run=self.dry_run)
        send(client, config)

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
            gcp_client.access_secret_version(
                name=uri,
            ).payload.data.decode("UTF-8"),
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
                private_key=private_key,
            )
    except Exception as e:
        logger.exception(e)
        logger.warning(
            "We have failed to load the private key, however, we will fallback to the PAT method.",
        )

    return Config(
        gh_app,
        GitHubConfig(
            # This token is a PAT
            token=os.environ.get("GH_TOKEN"),
            webhook_secret=os.environ.get("GH_WEBHOOK_SECRET"),
        ),
    )
