from __future__ import annotations

import gzip
import hashlib
import io
import logging
import uuid
from datetime import datetime
from urllib.parse import urlencode

import requests
from sentry_sdk.envelope import Envelope
from sentry_sdk.utils import Dsn
from sentry_sdk.utils import format_timestamp

from src import REQUEST_TIMEOUT

GITHUB_API_URL = "https://api.github.com"


class GithubSentryError(Exception):
    pass


def get_uuid():
    return uuid.uuid4().hex


def get_uuid_from_string(input_string):
    hash_object = hashlib.sha256(input_string.encode())
    hash_value = hash_object.hexdigest()
    return uuid.UUID(hash_value[:32]).hex


class GithubClient:
    # This transform GH jobs conclusion keywords to Sentry performance status
    github_status_trace_status = {"success": "ok", "failure": "internal_error"}

    def __init__(self, token, dsn, dry_run=False) -> None:
        self.token = token
        self.dry_run = dry_run
        # Orgs write the DSN into their .sentry repo by hand; raises BadDsn if it's invalid
        auth = Dsn(dsn).to_auth()
        self.sentry_key = auth.public_key
        # '{SCHEME}://{HOST}{PATH}api/{PROJECT_ID}/envelope/'
        self.sentry_project_url = auth.get_api_url()

    def _fetch_github(self, url):
        # The URL comes from the webhook payload, so only ever send the token to GitHub's API
        if not url.startswith(f"{GITHUB_API_URL}/"):
            raise GithubSentryError(f"Not a GitHub API URL: {url}")
        headers = {"Authorization": f"token {self.token}"}

        # Rebuilding the URL on our own base lets CodeQL see that its host is fixed
        req = requests.get(
            GITHUB_API_URL + url[len(GITHUB_API_URL) :],
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        req.raise_for_status()
        return req

    def _get_extra_metadata(self, job):
        # XXX: This is the slowest call
        runs = self._fetch_github(job["run_url"]).json()
        repo = runs["repository"]["full_name"]
        meta = {
            # "workflow_name": workflow["name"],
            "author": runs["head_commit"]["author"],
            # https://getsentry.atlassian.net/browse/TET-22
            # Tags are not linkified externally, plain text data can be selected in browsers and opened
            "data": {
                "job": job["html_url"],
            },
            "tags": {
                # e.g. success, failure, skipped
                "job_status": job["conclusion"],
                "branch": runs["head_branch"],
                "commit": runs["head_sha"],
                "repo": repo,
                "run_attempt": runs["run_attempt"],  # Rerunning a job
                "event": runs["event"],
                # It allows querying jobs within the same workflow (e.g. foo.yml)
                # The run has the path, so there's no need to fetch its workflow, which
                # fails for required workflows (`workflow_url` 422s). Their path can end
                # in a ref (e.g. `foo.yml@refs/heads/main`), which isn't part of the name
                "workflow": _workflow_file(runs),
            },
        }
        if runs.get("pull_requests"):
            pr_number = runs["pull_requests"][0]["number"]
            meta["data"]["pr"] = f"https://github.com/{repo}/pull/{pr_number}"
            meta["tags"]["pull_request"] = pr_number
        if job["conclusion"] == "failure":
            failing_steps = [
                step for step in job["steps"] if step["conclusion"] == "failure"
            ]
            if len(failing_steps) > 0:
                meta["tags"]["failing_step"] = failing_steps[0]["name"]

        return meta

    # Documentation about traces, transactions and spans
    # https://docs.sentry.io/product/sentry-basics/tracing/distributed-tracing/#traces
    # https://develop.sentry.dev/sdk/performance/
    def _generate_trace(self, job):
        meta = self._get_extra_metadata(job)
        transaction = _base_transaction(job)
        transaction["user"] = meta["author"]
        transaction["tags"] = meta["tags"]
        transaction["contexts"]["trace"]["data"] = meta["data"]

        # Transactions have name, spans don't.
        transaction["contexts"]["trace"]["op"] = job["name"]
        transaction["contexts"]["trace"]["description"] = job["name"]
        transaction["contexts"]["trace"][
            "status"
        ] = self.github_status_trace_status.get(job["conclusion"], "unimplemented")
        transaction["spans"] = _generate_spans(
            job["steps"],
            transaction["contexts"]["trace"]["span_id"],
            transaction["contexts"]["trace"]["trace_id"],
        )
        return transaction

    def _send_envelope(self, trace):
        if self.dry_run:
            return
        envelope = Envelope()
        envelope.add_transaction(trace)
        now = datetime.utcnow()

        headers = {
            "event_id": get_uuid(),  # Does this have to match anything?
            "sent_at": format_timestamp(now),
            "Content-Type": "application/x-sentry-envelope",
            "Content-Encoding": "gzip",
            "X-Sentry-Auth": f"Sentry sentry_key={self.sentry_key},"
            + f"sentry_client=gha-sentry/0.0.1,sentry_timestamp={now},"
            + "sentry_version=7",
        }

        body = io.BytesIO()
        with gzip.GzipFile(fileobj=body, mode="w") as f:
            envelope.serialize_into(f)

        req = requests.post(
            self.sentry_project_url,
            data=body.getvalue(),
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        req.raise_for_status()
        return req

    def send_commit_trace(self, workflow_run, commit_workflows=frozenset()):
        """Send a `ci.commit` trace if this workflow run turned its commit green.

        The job traces describe one job each, so they can't tell how long a commit
        took to go green: from its first workflow run being created until the last
        of its workflow runs passes. When a run succeeds, list every workflow run
        for its commit and, once all of them have passed, send one transaction
        spanning the commit, with a child span per workflow run.

        `commit_workflows` limits which workflow files have to pass (e.g. the ones
        behind required checks); by default every workflow run for the commit does.
        """
        # Neither of these can turn the commit green, so don't spend an API call
        if workflow_run["conclusion"] != "success":
            return
        if commit_workflows and _workflow_file(workflow_run) not in commit_workflows:
            return
        runs = self._fetch_github(_commit_runs_url(workflow_run)).json()
        trace = _generate_commit_trace(workflow_run, runs, commit_workflows)
        if trace:
            return self._send_envelope(trace)

    def send_trace(self, job):
        # This can happen when the workflow is skipped and there are no steps
        if job["conclusion"] == "skipped":
            logging.info(
                f"We are ignoring '{job['name']}' because it was skipped -> {job['html_url']}",
            )
            return
        trace = self._generate_trace(job)
        if trace:
            return self._send_envelope(trace)


def _base_transaction(job):
    return {
        "event_id": get_uuid(),
        # The distinctive feature of a Transaction is type: "transaction".
        "type": "transaction",
        "transaction": job["name"],
        "contexts": {
            "trace": {
                "span_id": get_uuid()[:16],
                # This trace id is basically just a hash from run_id and run_attempt turned into a uuid. We use it to trace jobs within a workflow.
                # `run_id` identifiess a particular workflow run and does not increment when rerunning jobs. This is why we also use `run_attempt` in the job.
                # https://docs.github.com/en/actions/learn-github-actions/contexts
                # https://docs.github.com/en/webhooks/webhook-events-and-payloads#workflow_job
                "trace_id": get_uuid_from_string(
                    "run_id:"
                    + str(job["run_id"])
                    + "run_attempt:"
                    + str(job["run_attempt"])
                ),
                "type": "trace",
            },
        },
        "user": {},
        # When ingesting old data during development (e.g. using fixtures), Sentry's UI will
        # show an error for transactions with "Clock drift detected in SDK"; It is harmeless.
        "start_timestamp": job["started_at"],
        "timestamp": job["completed_at"],
    }


# https://develop.sentry.dev/sdk/event-payloads/span/
def _generate_spans(steps, parent_span_id, trace_id):
    spans = []
    for step in steps:
        try:
            spans.append(
                {
                    "op": step["name"],
                    "name": step["name"],
                    "parent_span_id": parent_span_id,
                    "span_id": get_uuid()[:16],
                    "start_timestamp": step["started_at"],
                    "timestamp": step["completed_at"],
                    "trace_id": trace_id,
                },
            )
        except Exception as e:
            logging.exception(e)
    return spans


COMMIT_OP = "ci.commit"
COMMIT_TRANSACTION = "commit to green"
# A run with any of these conclusions doesn't stop its commit from going green
PASSING_CONCLUSIONS = {"success", "skipped", "neutral"}
# One page of runs; a commit with more workflow runs than this is skipped rather
# than spending more of the installation's API budget on it
RUNS_PER_PAGE = 100


def _commit_runs_url(workflow_run: dict) -> str:
    repo = workflow_run["repository"]["full_name"]
    query = urlencode(
        {
            "head_sha": workflow_run["head_sha"],
            # Keep push (e.g. master) and pull_request runs of the same commit apart
            "event": workflow_run["event"],
            "per_page": RUNS_PER_PAGE,
        }
    )
    return f"{GITHUB_API_URL}/repos/{repo}/actions/runs?{query}"


def _generate_commit_trace(
    workflow_run: dict, runs_response: dict, commit_workflows=frozenset()
) -> dict | None:
    """Build the commit transaction, or return None if this run shouldn't send one.

    Only the webhook for the run that turned the commit green sends the trace:
    every run must be completed and passing, and ``workflow_run`` must be the one
    that completed last. Each webhook reads the same list of runs, so when several
    runs finish at once, they agree on which one is last.
    """
    runs = runs_response.get("workflow_runs", [])
    if runs_response.get("total_count", len(runs)) > len(runs):
        logging.warning(
            "Not tracing commit %s, it has more than %s workflow runs",
            workflow_run["head_sha"],
            RUNS_PER_PAGE,
        )
        return None
    if commit_workflows:
        runs = [run for run in runs if _workflow_file(run) in commit_workflows]
    if not any(run["id"] == workflow_run["id"] for run in runs):
        # GitHub hasn't listed this run yet
        return None
    if any(run["status"] != "completed" for run in runs):
        # The last run to complete will trace the commit
        return None
    if any(run["conclusion"] not in PASSING_CONCLUSIONS for run in runs):
        # Not green (yet); re-running the failed run sends another webhook
        return None

    last_run = max(runs, key=lambda run: (run["updated_at"], run["id"]))
    if last_run["id"] != workflow_run["id"]:
        return None

    return _commit_transaction(workflow_run, runs, last_run)


def _commit_transaction(workflow_run: dict, runs: list, last_run: dict) -> dict:
    repo = workflow_run["repository"]["full_name"]
    sha = workflow_run["head_sha"]
    event = workflow_run["event"]
    # Deterministic, so a redelivered webhook sends a duplicate that's easy to spot
    trace_id = get_uuid_from_string(f"repo:{repo}commit:{sha}event:{event}")
    span_id = trace_id[:16]
    # Workflow runs are created as soon as GitHub gets the push or PR update.
    # head_commit.timestamp is when the commit was authored, which can be much earlier.
    start = min(run["created_at"] for run in runs)

    tags = {
        "ci_result": "green",
        "repo": repo,
        "branch": workflow_run["head_branch"],
        "commit": sha,
        "event": event,
        "workflow_runs": len(runs),
        # Time to green includes waiting for someone to re-run a failed workflow
        "rerun": str(any(run.get("run_attempt", 1) > 1 for run in runs)).lower(),
        "last_workflow": _workflow_file(last_run),
    }
    data = {"commit": f"https://github.com/{repo}/commit/{sha}"}
    # A push to master also lists forks' PRs whose head is our master, so only keep
    # PRs into this repo
    pull_requests = [
        pr
        for pr in workflow_run.get("pull_requests") or []
        if pr["base"]["repo"]["url"] == f"{GITHUB_API_URL}/repos/{repo}"
    ]
    if pull_requests:
        pr_number = pull_requests[0]["number"]
        tags["pull_request"] = pr_number
        tags["base_branch"] = pull_requests[0]["base"]["ref"]
        data["pr"] = f"https://github.com/{repo}/pull/{pr_number}"

    author = (workflow_run.get("head_commit") or {}).get("author") or {}
    return {
        "event_id": get_uuid(),
        "type": "transaction",
        "transaction": COMMIT_TRANSACTION,
        "contexts": {
            "trace": {
                "op": COMMIT_OP,
                "description": COMMIT_TRANSACTION,
                "span_id": span_id,
                "trace_id": trace_id,
                "type": "trace",
                "status": "ok",
                "data": data,
            },
        },
        "user": author,
        "tags": tags,
        "start_timestamp": start,
        "timestamp": last_run["updated_at"],
        "spans": [
            {
                "op": _workflow_file(run),
                "description": run["name"],
                "parent_span_id": span_id,
                "span_id": get_uuid()[:16],
                "trace_id": trace_id,
                # created_at rather than run_started_at, so queueing counts
                "start_timestamp": run["created_at"],
                "timestamp": run["updated_at"],
                "status": "ok",
                "data": {
                    "run": run["html_url"],
                    "run_attempt": run.get("run_attempt", 1),
                    "conclusion": run["conclusion"],
                },
            }
            for run in sorted(runs, key=lambda run: run["created_at"])
        ],
    }


def _workflow_file(run: dict) -> str:
    # e.g. `backend.yml`. A run's path can name the repo the workflow lives in and end
    # in a ref (e.g. `org/repo/.github/workflows/foo.yml@refs/heads/main`)
    return run["path"].split("@", 1)[0].rsplit("/")[-1]
