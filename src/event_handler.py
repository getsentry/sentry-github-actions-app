import hmac
import hashlib
import json

from .github_sdk import GithubClient


class EventHandler:
    def __init__(self, token=None, secret=None, dsn=None, dry_run=False):
        self.secret = secret
        self.client = GithubClient(token=token, dsn=dsn, dry_run=dry_run)

    def handle_event(self, data, headers):
        # We return 200 to make webhook not turn red since everything got processed well
        http_code = 200
        reason = "OK"

        if self.secret and not valid_payload(
            self.secret, data, headers["X-Hub-Signature"].replace("sha1=", "")
        ):
            http_code = 400
            reason = "The secret you are using on your Github webhook does not match this app's secret."
        elif headers["X-GitHub-Event"] != "workflow_job":
            reason = "Event not supported."
        elif data["action"] != "completed":
            reason = "We cannot do anything with this workflow state."
        else:
            self.client.send_trace(data["workflow_job"])

        return reason, http_code


def payload_signature(secret, payload):
    return hmac.new(
        secret.encode("utf-8"), json.dumps(payload).encode("utf-8"), hashlib.sha1
    ).hexdigest()


def valid_payload(secret, payload, signature):
    # Validate payload signature
    return hmac.compare_digest(payload_signature(secret, payload), signature)
