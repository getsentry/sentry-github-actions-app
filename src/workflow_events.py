import gzip
import io
import logging
import os
import uuid
from datetime import datetime

import requests
from sentry_sdk import capture_exception
from sentry_sdk.envelope import Envelope
from sentry_sdk.utils import format_timestamp

LOGGING_LEVEL = os.environ.get("LOGGING_LEVEL", "INFO")
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)

# We need an authorized token to fetch the API. If you have SSO on your org you will need to grant permission
# Your app and the Github webhook will share this secret
# You can create an .env file and place the token in it
GH_TOKEN = os.environ.get("GH_TOKEN")
# Where to report Github actions transactions
SENTRY_GITHUB_DSN = os.environ.get("SENTRY_GITHUB_DSN")

def base_transaction():
    trace_id = uuid.uuid4().hex
    parent_span_id = uuid.uuid4().hex[16:]
    return {
        "event_id": uuid.uuid4().hex,
        "type": "transaction",
        "transaction": "default",
        "contexts": {
            "trace": {
                "trace_id": trace_id,
                "span_id": parent_span_id,
                "type": "trace",
            },
        },
    }

def get(url):
    headers = {}
    if GH_TOKEN and url.find("github.com") >= 0:
        headers["Authorization"] = f"token {GH_TOKEN}"
    req = requests.get(url, headers=headers)
    if not req.ok:
        raise Exception(req.text)
    return req

def send_envelope(envelope):
    base_uri, project_id = SENTRY_GITHUB_DSN.rsplit("/", 1)
    sentry_key = base_uri.rsplit('@')[0].rsplit('https://')[1]
    headers = {
        "event_id": uuid.uuid4().hex,  # Does this have to match anything?
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
    if not req.ok:
        raise Exception(req.text)
    return req


def get_extra_metadata(workflow_run):
    req = get(workflow_run)
    if not req.ok:
        raise Exception(req.text)
    run_data = req.json()
    # XXX: We could enrich each transaction by having access to the yml file and/or the logs
    return get(run_data["workflow_url"]).json()


def determine_job_name(workflow):
    job_name = workflow["name"]
    try:
        # This helps to have human friendly transaction names
        meta = get_extra_metadata(workflow["run_url"])
        job_name = f'{meta["name"]}/{workflow["name"]}'
    except Exception as e:
        capture_exception(e)
        logging.exception(e)
        logging.error(f"Failed to process -> {workflow['run_url']}")

    return job_name


def _generate_transaction(workflow, job_name):
    transaction = base_transaction()
    transaction["transaction"] = job_name
    # When processing old data during development, in Sentry's UI, you will
    # see an error for transactions with "Clock drift detected in SDK";
    # It is harmeless.
    transaction["start_timestamp"] = workflow["started_at"]
    transaction["timestamp"] = workflow["completed_at"]
    transaction["contexts"]["trace"]["op"] = workflow["name"]
    # XXX: Determine what the failure state should look like
    transaction["contexts"]["trace"]["status"] = (
        "ok" if workflow["conclusion"] == "success" else "TBD"
    )
    transaction["contexts"]["trace"]["data"] = (workflow["html_url"],)
    # html_url points to the UI showing the job run
    # url points has the data to generate this transaction
    # run_url has extra metadata about the workflow file
    transaction["contexts"]["trace"]["tags"] = {
        "html_url": workflow["html_url"],
        "url": workflow["url"],
        "run_url": workflow["run_url"],
    }
    return transaction


def _generate_spans(steps, parent_span_id, trace_id):
    spans = []
    for step in steps:
        try:
            spans.append(
                {
                    "op": step["name"],
                    "parent_span_id": parent_span_id,
                    "span_id": uuid.uuid4().hex[16:],
                    "start_timestamp": step["started_at"],
                    "timestamp": step["completed_at"],
                    "trace_id": trace_id,
                }
            )
        except Exception as e:
            capture_exception(e)
            logging.exception(e)
    return spans


# Documentation about traces, transactions and spans
# https://docs.sentry.io/product/sentry-basics/tracing/distributed-tracing/#traces
def generate_transaction(workflow, job_name):
    # This can happen when the workflow is skipped and there are no steps
    if not workflow["steps"]:
        logging.warn(f"We are ignoring {workflow['name']} -> {workflow['html_url']}")
        return

    transaction = _generate_transaction(workflow, job_name)
    transaction["spans"] = _generate_spans(
        workflow["steps"],
        transaction["contexts"]["trace"]["span_id"],
        transaction["contexts"]["trace"]["trace_id"],
    )
    return transaction


def generate_event(workflow, job_name):
    for step in workflow["steps"]:
        if step["conclusion"] != "success":
            return {
                "message": f"{job_name} failed",
                "level": "error",
                "tags": {"url": f'{workflow["html_url"]}/?check_suite_focus=true'},
            }


def process_data(data):
    workflow_job = data["workflow_job"]
    # XXX: We can probably cache the function call rather than have to pass it down via parameter
    job_name = determine_job_name(workflow_job)
    envelope = Envelope()
    transaction = generate_transaction(workflow_job, job_name)
    if transaction:
        envelope.add_transaction(transaction)
    if workflow_job["conclusion"] == "failure":
        event = generate_event(workflow_job, job_name)
        envelope.add_event(event)
    if envelope.items:
        send_envelope(envelope)
