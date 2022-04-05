import sys

from trace import get, generate_trace

# Point this script to the URL of a job and we will trace it
# You give us this https://github.com/getsentry/sentry/runs/5759197422?check_suite_focus=true
# Or give it a path to a file with a webhook payload
# e.g. tests/fixtures/failed_workflow.json
if __name__ == "__main__":
    argument = sys.argv[1]
    if argument.startswith("https"):
        _, _, _, org, repo, _, run_id = argument.split("?")[0].split("/")
        url = f"https://api.github.com/repos/{org}/{repo}/actions/jobs/{run_id}"
        req = get(url)
        if not req.ok:
            raise Exception(req.text)
        generate_trace(req.json())
    else:
        import json

        data = {}
        with open(argument) as f:
            data = json.load(f)
        # XXX: Switch over to handle_event
        generate_trace(data["workflow_job"])
