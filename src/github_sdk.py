import gzip
import io
import logging
import os
import uuid
from datetime import datetime

import requests
from sentry_sdk.envelope import Envelope
from sentry_sdk.utils import format_timestamp

logging.basicConfig(level=os.environ.get("LOGGING_LEVEL", "INFO"))

# We need an authorized token to fetch the API. If you have SSO on your org you will need to grant permission
# Your app and the Github webhook will share this secret
# You can create an .env file and place the token in it
GH_TOKEN = os.environ.get("GH_TOKEN")
# Where to report Github actions transactions
SENTRY_GITHUB_DSN = os.environ.get("SENTRY_GITHUB_DSN")


class GithubSentryError(Exception):
    pass


def get(url):
    headers = {}
    if GH_TOKEN and url.find("github.com") >= 0:
        headers["Authorization"] = f"token {GH_TOKEN}"
    req = requests.get(url, headers=headers)
    if not req.ok:
        raise Exception(req.text)
    return req


def get_uuid():
    return uuid.uuid4().hex


def send_envelope(trace):
    if not SENTRY_GITHUB_DSN:
        raise GithubSentryError("Set SENTRY_GITHUB_SDN in order to send envelopes.")
    envelope = Envelope()
    envelope.add_transaction(trace)
    base_uri, project_id = SENTRY_GITHUB_DSN.rsplit("/", 1)
    sentry_key = base_uri.rsplit("@")[0].rsplit("https://")[1]
    headers = {
        "event_id": get_uuid(),  # Does this have to match anything?
        "sent_at": format_timestamp(datetime.utcnow()),
        "Content-Type": "application/x-sentry-envelope",
        "Content-Encoding": "gzip",
        "X-Sentry-Auth": f"Sentry sentry_key={sentry_key},"
        + f"sentry_client=gha-sentry/0.0.1,sentry_timestamp={str(datetime.utcnow())},"
        + "sentry_version=7",
    }

    # '{BASE_URI}/api/{PROJECT_ID}/{ENDPOINT}/'
    url = f"{base_uri}/api/{project_id}/envelope/"
    if GH_TOKEN and url.find("github.com") >= 0:
        headers["Authorization"] = f"token {GH_TOKEN}"

    body = io.BytesIO()
    with gzip.GzipFile(fileobj=body, mode="w") as f:
        envelope.serialize_into(f)

    req = requests.post(url, data=body.getvalue(), headers=headers)
    req.raise_for_status()


# XXX: This is a slow call
def get_extra_metadata(job):
    runs = get(job["run_url"]).json()
    workflow = get(runs["workflow_url"]).json()
    repo = runs["head_repository"]["full_name"]
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


github_status_trace_status = {"success": "ok", "failure": "internal_error"}
# Documentation about traces, transactions and spans
# https://docs.sentry.io/product/sentry-basics/tracing/distributed-tracing/#traces
# https://develop.sentry.dev/sdk/performance/
def _generate_trace(job):
    meta = get_extra_metadata(job)
    transaction = _base_transaction(job)
    transaction["user"] = meta["author"]
    transaction["tags"] = meta["tags"]
    transaction["contexts"]["trace"]["data"] = meta["data"]

    # Transactions have name, spans don't.
    transaction["contexts"]["trace"]["op"] = job["name"]
    transaction["contexts"]["trace"]["description"] = job["name"]
    transaction["contexts"]["trace"]["status"] = github_status_trace_status.get(
        job["conclusion"], "unimplemented"
    )
    transaction["spans"] = _generate_spans(
        job["steps"],
        transaction["contexts"]["trace"]["span_id"],
        transaction["contexts"]["trace"]["trace_id"],
    )
    return transaction


def send_trace(workflow):
    # This can happen when the workflow is skipped and there are no steps
    if workflow["conclusion"] == "skipped":
        logging.info(
            f"We are ignoring '{workflow['name']}' because it was skipped -> {workflow['html_url']}"
        )
        return
    trace = _generate_trace(workflow)
    if trace:
        send_envelope(trace)
