import hmac
import logging
import os
from typing import NamedTuple

from .github_sdk import GithubClient

LOGGING_LEVEL = os.environ.get("LOGGING_LEVEL", logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)


class WebAppHandler:
    def __init__(self, dry_run=False):
        self.config = init_config()
        self.gh_client = GithubClient(
            token=self.config["gh"]["token"],
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
                msg=str(body).encode(),
                digestmod="sha256",
            ).hexdigest()
            return hmac.compare_digest(body_signature, signature)


class GitHubConfig(NamedTuple):
    webhook_secret: str | None
    token: str | None


class SentryConfig(NamedTuple):
    dsn: str | None


class Config(NamedTuple):
    gh: GitHubConfig
    sentry: SentryConfig


def init_config():
    config = Config()
    config.gh = GitHubConfig(
        token=os.environ.get("GH_TOKEN"),
        webhook_secret=os.environ.get("GH_WEBHOOK_SECRET"),
    )
    config.sentry = SentryConfig(dsn=os.environ.get("SENTRY_GITHUB_DSN"))

    return config
