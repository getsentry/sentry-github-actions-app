import gzip
import io
import logging
import uuid
from datetime import datetime

import requests
from sentry_sdk.envelope import Envelope
from sentry_sdk.utils import format_timestamp


class GithubSentryError(Exception):
    pass


def get_uuid():
    return uuid.uuid4().hex


class GithubClient:
    # This transform GH jobs conclusion keywords to Sentry performance status
    github_status_trace_status = {"success": "ok", "failure": "internal_error"}

    def __init__(self, token, dsn, github_app=False, dry_run=False) -> None:
        self.dry_run = dry_run
        self.github_app = github_app
        self.token = token
        if dsn:
            base_uri, project_id = dsn.rsplit("/", 1)
            self.sentry_key = base_uri.rsplit("@")[0].rsplit("https://")[1]
            # '{BASE_URI}/api/{PROJECT_ID}/{ENDPOINT}/'
            self.sentry_project_url = f"{base_uri}/api/{project_id}/envelope/"

    def _fetch_github(self, url):
        headers = {}
        # Support JWT token for Github apps
        if self.github_app:
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "Authorization": f"Bearer {self.token}",
            }
        else:
            headers["Authorization"] = f"token {self.token}"

        req = requests.get(url, headers=headers)
        req.raise_for_status()
        return req

    def _get_extra_metadata(self, job):
        # XXX: This is the slowest call
        runs = self._fetch_github(job["run_url"]).json()
        workflow = self._fetch_github(runs["workflow_url"]).json()
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
                "job_status": job["conclusion"],  # e.g. success, failure, skipped
                "branch": runs["head_branch"],
                "commit": runs["head_sha"],
                "repo": repo,
                "run_attempt": runs["run_attempt"],  # Rerunning a job
                # It allows querying jobs within the same workflow (e.g. foo.yml)
                "workflow": workflow["path"].rsplit("/")[-1],
            },
        }
        if runs.get("pull_requests"):
            pr_number = runs["pull_requests"][0]["number"]
            meta["data"]["pr"] = f"https://github.com/{repo}/pull/{pr_number}"
            meta["tags"]["pull_request"] = pr_number

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
            self.sentry_project_url, data=body.getvalue(), headers=headers
        )
        req.raise_for_status()
        return req

    def send_trace(self, job):
        # This can happen when the workflow is skipped and there are no steps
        if job["conclusion"] == "skipped":
            logging.info(
                f"We are ignoring '{job['name']}' because it was skipped -> {job['html_url']}"
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
                "trace_id": get_uuid(),
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
                }
            )
        except Exception as e:
            logging.exception(e)
    return spans
