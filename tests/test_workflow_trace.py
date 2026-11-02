from __future__ import annotations

import json

import pytest
import responses

from src.github_sdk import _generate_workflow_trace
from src.github_sdk import _run_jobs_url
from src.github_sdk import GithubClient
from src.sentry_config import SENTRY_CONFIG_API_URL
from src.web_app_handler import WebAppHandler
from tests.test_sentry_config_file import config_file_meta

DSN = "https://foo@random.ingest.sentry.io/1234"
ENVELOPE_URL = "https://random.ingest.sentry.io/api/1234/envelope/"


@pytest.fixture
def webhook_payload():
    with open("tests/fixtures/commit/webhook_payload.json") as f:
        return json.load(f)


@pytest.fixture
def workflow_run(webhook_payload):
    return webhook_payload["workflow_run"]


@pytest.fixture
def jobs(jobA_job, failure_job, skipped_workflow):
    return {"total_count": 3, "jobs": [jobA_job, failure_job, skipped_workflow]}


def test_run_jobs_url(workflow_run):
    assert _run_jobs_url(workflow_run) == (
        "https://api.github.com/repos/getsentry/sentry/actions/runs/38468300492/jobs"
        "?per_page=100"
    )


def test_workflow_trace(workflow_run, jobs, jobA_job, failure_job):
    trace = _generate_workflow_trace(workflow_run, jobs)

    assert trace["transaction"] == "backend"
    assert trace["contexts"]["trace"]["op"] == "ci.workflow"
    assert trace["contexts"]["trace"]["status"] == "ok"
    assert trace["tags"]["workflow"] == "backend.yml"
    assert trace["tags"]["workflow_status"] == "success"
    # It spans every job, including ones that ran before this attempt started
    assert trace["start_timestamp"] == jobA_job["started_at"]
    assert trace["timestamp"] == workflow_run["updated_at"]

    root = trace["contexts"]["trace"]["span_id"]
    job_spans = [span for span in trace["spans"] if span["op"] == "ci.job"]
    # The skipped job is left out
    assert [span["description"] for span in job_spans] == ["frontend tests (0)", "test"]
    assert all(span["parent_span_id"] == root for span in job_spans)
    assert [span["status"] for span in job_spans] == ["ok", "internal_error"]

    step_spans = [span for span in trace["spans"] if span["op"] != "ci.job"]
    assert len(step_spans) == len(jobA_job["steps"]) + len(failure_job["steps"])
    for job_span, job in zip(job_spans, [jobA_job, failure_job]):
        children = [s for s in step_spans if s["parent_span_id"] == job_span["span_id"]]
        assert [s["op"] for s in children] == [step["name"] for step in job["steps"]]
    assert all(
        span["trace_id"] == trace["contexts"]["trace"]["trace_id"]
        for span in trace["spans"]
    )


def test_workflow_trace_skips_runs_with_more_jobs_than_a_page(workflow_run, jobs):
    jobs["total_count"] = 101
    assert _generate_workflow_trace(workflow_run, jobs) is None


@responses.activate
def test_skipped_run_makes_no_api_calls(workflow_run):
    workflow_run["conclusion"] = "skipped"
    assert GithubClient(dsn=DSN, token="t").send_workflow_trace(workflow_run) is None
    assert len(responses.calls) == 0


@responses.activate
def test_send_workflow_trace(workflow_run, jobs):
    responses.get(_run_jobs_url(workflow_run), json=jobs)
    responses.post(ENVELOPE_URL)

    GithubClient(dsn=DSN, token="t").send_workflow_trace(workflow_run)

    responses.assert_call_count(ENVELOPE_URL, 1)


@pytest.mark.parametrize("orgs", ["", "other-org", "getsentry-fork"])
def test_workflow_traces_are_opt_in_per_org(monkeypatch, webhook_payload, orgs):
    monkeypatch.delenv("COMMIT_TRACES_ENABLED", raising=False)
    monkeypatch.setenv("WORKFLOW_TRACES_ORGS", orgs)
    reason, _ = WebAppHandler().handle_event(
        data=webhook_payload, headers={"X-GitHub-Event": "workflow_run"}
    )
    assert reason == "Workflow run traces are not enabled."


@responses.activate
def test_failed_workflow_run_sends_workflow_trace(monkeypatch, webhook_payload, jobs):
    monkeypatch.delenv("GH_APP_ID", raising=False)
    monkeypatch.setenv("GH_TOKEN", "pat")
    monkeypatch.setenv("COMMIT_TRACES_ENABLED", "true")
    monkeypatch.setenv("WORKFLOW_TRACES_ORGS", "other-org, getsentry")
    webhook_payload["workflow_run"]["conclusion"] = "failure"
    with open("tests/fixtures/commit/runs.json") as f:
        runs = json.load(f)

    responses.get(
        SENTRY_CONFIG_API_URL.replace("{owner}", "getsentry"),
        json=config_file_meta(DSN),
    )
    jobs_url = responses.get(_run_jobs_url(webhook_payload["workflow_run"]), json=jobs)
    runs_url = responses.get(
        "https://api.github.com/repos/getsentry/sentry/actions/runs", json=runs
    )
    responses.post(ENVELOPE_URL)

    reason, http_code = WebAppHandler().handle_event(
        data=webhook_payload, headers={"X-GitHub-Event": "workflow_run"}
    )

    assert (reason, http_code) == ("OK", 200)
    assert jobs_url.call_count == 1
    # A failed run can't turn the commit green
    assert runs_url.call_count == 0
    responses.assert_call_count(ENVELOPE_URL, 1)
