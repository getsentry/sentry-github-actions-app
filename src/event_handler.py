import hmac

from .github_sdk import GithubClient


class EventHandler:
    def __init__(self, token=None, secret=None, dsn=None, dry_run=False):
        self.secret = secret
        self.client = GithubClient(token=token, dsn=dsn, dry_run=dry_run)

    def handle_event(self, data, headers):
        # We return 200 to make webhook not turn red since everything got processed well
        http_code = 200
        reason = "OK"

        if headers["X-GitHub-Event"] != "workflow_job":
            reason = "Event not supported."
        elif data["action"] != "completed":
            reason = "We cannot do anything with this workflow state."
        else:
            self.client.send_trace(data["workflow_job"])

        return reason, http_code

    def valid_signature(self, body, headers):
        if not self.secret:
            return True
        else:
            signature = headers["X-Hub-Signature-256"].replace("sha256=", "")
            body_signature = hmac.new(
                self.secret.encode(), msg=body, digestmod="sha256"
            ).hexdigest()
            return hmac.compare_digest(body_signature, signature)
