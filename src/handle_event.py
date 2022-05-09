import os
from .github_sdk import send_trace


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
        send_trace(data["workflow_job"])

    return reason, http_code
