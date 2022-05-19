from .github_sdk import GithubClient


class EventHandler:
    def __init__(self, token=None, dsn=None):
        self.client = GithubClient(token=token, dsn=dsn)

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
