from __future__ import annotations

import base64
import hmac
import logging
import os
from typing import NamedTuple

import requests

from .github_app import GithubAppToken
from .github_sdk import GithubClient
from .workflow_job_collector import WorkflowJobCollector

LOGGING_LEVEL = os.environ.get("LOGGING_LEVEL", logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)


class WebAppHandler:
    """
    Handles GitHub webhook events for workflow job completion.
    
    Supports both hierarchical workflow tracing (new) and individual job tracing (legacy).
    The mode is controlled by the ENABLE_HIERARCHICAL_TRACING environment variable.
    """
    
    def __init__(self, dry_run=False):
        """
        Initialize the WebAppHandler.
        
        Args:
            dry_run: If True, simulates operations without sending traces
        """
        self.config = init_config()
        self.dry_run = dry_run
        self.job_collectors = {}  # org -> WorkflowJobCollector
        
    def _get_job_collector(self, org: str, token: str, dsn: str) -> WorkflowJobCollector:
        """
        Get or create a job collector for the organization.
        
        Args:
            org: GitHub organization name
            token: GitHub API token
            dsn: Sentry DSN for trace submission
            
        Returns:
            WorkflowJobCollector instance for the organization
        """
        if org not in self.job_collectors:
            self.job_collectors[org] = WorkflowJobCollector(dsn, token, self.dry_run)
        return self.job_collectors[org]

    def _send_legacy_trace(self, data: dict, org: str, token: str, dsn: str) -> None:
        """
        Send individual job trace (legacy behavior).
        
        Args:
            data: GitHub webhook job payload
            org: GitHub organization name
            token: GitHub API token
            dsn: Sentry DSN for trace submission
        """
        logger.info(f"Using legacy individual job tracing for org '{org}'")
        github_client = GithubClient(token, dsn, self.dry_run)
        github_client.send_trace(data)

    def handle_event(self, data, headers):
        """
        Handle GitHub webhook events.
        
        Supports both hierarchical workflow tracing (new) and individual job tracing (legacy).
        The mode is determined by feature flags and organization settings.
        
        Args:
            data: GitHub webhook payload
            headers: HTTP headers from the webhook request
            
        Returns:
            Tuple of (reason, http_code)
        """
        http_code = 200
        reason = "OK"

        # Flask normalizes headers - try both original and normalized names
        github_event = headers.get("X-GitHub-Event") or headers.get("X-GITHUB-EVENT") or headers.get("HTTP_X_GITHUB_EVENT")
        if not github_event:
            reason = "Missing X-GitHub-Event header."
            http_code = 400
            logger.warning("Missing X-GitHub-Event header")
        elif github_event != "workflow_job":
            reason = "Event not supported."
            logger.info(f"Event '{github_event}' not supported, only 'workflow_job' is supported")
        elif data.get("action") != "completed":
            reason = "We cannot do anything with this workflow state."
            logger.info(f"Action '{data.get('action')}' not supported, only 'completed' is supported")
        else:
            # Log webhook received
            workflow_job = data.get("workflow_job", {})
            run_id = workflow_job.get("run_id")
            job_id = workflow_job.get("id")
            job_name = workflow_job.get("name")
            logger.info(f"Received webhook for workflow run {run_id}, job '{job_name}' (ID: {job_id})")
            if self.dry_run:
                return reason, http_code

            # Handle missing installation field (for webhook testing)
            installation_id = data.get("installation", {}).get("id")
            org = data["repository"]["owner"]["login"]

            # For webhook testing, use the DSN directly from environment
            dsn = os.environ.get("APP_DSN")
            if not dsn:
                reason = "No DSN configured for webhook testing"
                http_code = 500
            else:
                # Get GitHub App installation token if available, otherwise fall back to PAT or None
                token = None
                if installation_id and self.config.gh_app:
                    try:
                        # Generate installation token from GitHub App
                        github_app_token = GithubAppToken(
                            self.config.gh_app.private_key,
                            self.config.gh_app.app_id
                        )
                        # Note: We use the token immediately, not in a context manager
                        # because we need it to persist for the WorkflowJobCollector
                        # The token expires after 1 hour, which is fine for our use case
                        token_response = requests.post(
                            url=f"https://api.github.com/app/installations/{installation_id}/access_tokens",
                            headers=github_app_token.headers,
                        )
                        token_response.raise_for_status()
                        token = token_response.json()["token"]
                        logger.debug(f"Generated GitHub App installation token for org '{org}'")
                    except Exception as e:
                        logger.warning(
                            f"Failed to generate GitHub App installation token for org '{org}': {e}. "
                            "Falling back to timeout-based job detection."
                        )
                        # Fall back to PAT if available
                        token = self.config.gh.token
                elif self.config.gh.token:
                    # Use PAT if GitHub App is not configured
                    token = self.config.gh.token
                    logger.debug(f"Using PAT token for org '{org}'")
                else:
                    logger.debug(
                        f"No token available for org '{org}'. "
                        "Will use timeout-based job detection."
                    )
                
                # Get job collector and check if hierarchical tracing is enabled
                collector = self._get_job_collector(org, token, dsn)
                
                if collector.is_hierarchical_tracing_enabled(org):
                    # Use new hierarchical workflow tracing
                    logger.debug(f"Using hierarchical workflow tracing for org '{org}'")
                    collector.add_job(data)
                else:
                    # Fall back to legacy individual job tracing
                    self._send_legacy_trace(data, org, token, dsn)

        return reason, http_code

    def valid_signature(self, body, headers):
        if not self.config.gh.webhook_secret:
            return True
        else:
            # Flask normalizes headers - try both original and normalized names
            signature_header = headers.get("X-Hub-Signature-256") or headers.get("X-HUB-SIGNATURE-256") or headers.get("HTTP_X_HUB_SIGNATURE_256")
            if not signature_header:
                return False
            signature = signature_header.replace("sha256=", "")
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
