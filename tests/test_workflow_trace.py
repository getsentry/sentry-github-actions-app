from __future__ import annotations

from typing import Any

import pytest
import responses

from src.github_sdk import _generate_workflow_trace
from src.github_sdk import _run_jobs_url
from src.github_sdk import GithubClient
from src.sentry_config import SENTRY_CONFIG_API_URL
from src.web_app_handler import WebAppHandler
from tests.helpers import sentry_config_response

DSN = "https://foo@random.ingest.sentry.io/1234"
ENVELOPE_URL = "https://random.ingest.sentry.io/api/1234/envelope/"


@pytest.fixture
def workflow_run(commit_webhook_payload: dict[str, Any]) -> dict[str, Any]:
    run: dict[str, Any] = commit_webhook_payload["workflow_run"]
    return run


@pytest.fixture
def jobs(
    jobA_job: dict[str, Any],
    failure_job: dict[str, Any],
    skipped_workflow: dict[str, Any],
) -> dict[str, Any]:
    return {"total_count": 3, "jobs": [jobA_job, failure_job, skipped_workflow]}


def test_run_jobs_url(workflow_run: dict[str, Any]) -> None:
    assert _run_jobs_url(workflow_run) == (
        "https://api.github.com/repos/getsentry/sentry/actions/runs/38468300492/jobs"
        "?per_page=100"
    )


def test_workflow_trace(
    workflow_run: dict[str, Any],
    jobs: dict[str, Any],
    jobA_job: dict[str, Any],
    failure_job: dict[str, Any],
) -> None:
    trace = _generate_workflow_trace(workflow_run, jobs)
    assert trace is not None

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


def test_workflow_trace_skips_runs_with_more_jobs_than_a_page(
    workflow_run: dict[str, Any], jobs: dict[str, Any]
) -> None:
    jobs["total_count"] = 101
    assert _generate_workflow_trace(workflow_run, jobs) is None


@responses.activate
def test_skipped_run_makes_no_api_calls(workflow_run: dict[str, Any]) -> None:
    workflow_run["conclusion"] = "skipped"
    assert GithubClient(dsn=DSN, token="t").send_workflow_trace(workflow_run) is None
    assert len(responses.calls) == 0


@responses.activate
def test_send_workflow_trace(
    workflow_run: dict[str, Any], jobs: dict[str, Any]
) -> None:
    responses.get(_run_jobs_url(workflow_run), json=jobs)
    responses.post(ENVELOPE_URL)

    GithubClient(dsn=DSN, token="t").send_workflow_trace(workflow_run)

    responses.assert_call_count(ENVELOPE_URL, 1)


@pytest.mark.parametrize("orgs", ["", "other-org", "getsentry-fork"])
def test_workflow_traces_are_opt_in_per_org(
    monkeypatch: pytest.MonkeyPatch, commit_webhook_payload: dict[str, Any], orgs: str
) -> None:
    monkeypatch.setenv("WORKFLOW_TRACES_ORGS", orgs)
    reason, _ = WebAppHandler().handle_event(
        data=commit_webhook_payload, headers={"X-GitHub-Event": "workflow_run"}
    )
    assert reason == "Workflow run traces are not enabled."


@responses.activate
def test_failed_workflow_run_sends_workflow_trace(
    monkeypatch: pytest.MonkeyPatch,
    gh_app_env: None,
    commit_webhook_payload: dict[str, Any],
    commit_runs: dict[str, Any],
    jobs: dict[str, Any],
) -> None:
    monkeypatch.setenv("COMMIT_TRACES_ENABLED", "true")
    monkeypatch.setenv("WORKFLOW_TRACES_ORGS", "other-org, getsentry")
    workflow_run = commit_webhook_payload["workflow_run"]
    workflow_run["conclusion"] = "failure"

    responses.post(
        "https://api.github.com/app/installations/1/access_tokens",
        json={"token": "irrelevant"},
    )
    responses.delete("https://api.github.com/installation/token")
    responses.get(
        SENTRY_CONFIG_API_URL.replace("{owner}", "getsentry"),
        json=sentry_config_response(DSN),
    )
    jobs_url = responses.get(_run_jobs_url(workflow_run), json=jobs)
    runs_url = responses.get(
        "https://api.github.com/repos/getsentry/sentry/actions/runs", json=commit_runs
    )
    responses.post(ENVELOPE_URL)

    reason, http_code = WebAppHandler().handle_event(
        data=commit_webhook_payload, headers={"X-GitHub-Event": "workflow_run"}
    )

    assert (reason, http_code) == ("OK", 200)
    assert jobs_url.call_count == 1
    # A failed run can't turn the commit green
    assert runs_url.call_count == 0
    responses.assert_call_count(ENVELOPE_URL, 1)
