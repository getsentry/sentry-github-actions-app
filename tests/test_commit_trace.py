from __future__ import annotations

import copy
import json

import pytest
import responses

from src.github_sdk import _commit_runs_url
from src.github_sdk import _generate_commit_trace
from src.github_sdk import GithubClient
from src.web_app_handler import WebAppHandler

DSN = "https://foo@random.ingest.sentry.io/1234"
ENVELOPE_URL = "https://random.ingest.sentry.io/api/1234/envelope/"
TOKEN = "irrelevant"
SHA = "00450fe2d1b2ca30b58922ebd3ad7dce1b0a4293"
BACKEND_RUN_ID = 38468300492
ACCEPTANCE_RUN_ID = 38468300577


@pytest.fixture
def webhook_payload():
    with open("tests/fixtures/commit/webhook_payload.json") as f:
        return json.load(f)


@pytest.fixture
def workflow_run(webhook_payload):
    # backend.yml, the last of the commit's 10 workflow runs to complete
    return webhook_payload["workflow_run"]


@pytest.fixture
def commit_runs():
    with open("tests/fixtures/commit/runs.json") as f:
        return json.load(f)


def _run(runs, run_id):
    return next(run for run in runs["workflow_runs"] if run["id"] == run_id)


def test_commit_runs_url(workflow_run):
    assert _commit_runs_url(workflow_run) == (
        "https://api.github.com/repos/getsentry/sentry/actions/runs"
        f"?head_sha={SHA}&event=push&per_page=100"
    )


def test_commit_trace(workflow_run, commit_runs):
    trace = _generate_commit_trace(workflow_run, commit_runs)

    assert trace["type"] == "transaction"
    assert trace["transaction"] == "commit to green"
    assert trace["contexts"]["trace"]["op"] == "ci.commit"
    # The slowest workflow run, from its latest attempt starting to completing
    assert trace["start_timestamp"] == "2026-10-13T21:08:21Z"
    assert trace["timestamp"] == "2026-10-13T21:26:10Z"
    assert trace["tags"] == {
        "ci_result": "green",
        "repo": "getsentry/sentry",
        "branch": "master",
        "commit": SHA,
        "event": "push",
        "workflow_runs": 10,
        "rerun": "false",
        "slowest_workflow": "backend.yml",
    }
    # Forks' PRs don't make a push to master look like a PR
    assert "pr" not in trace["contexts"]["trace"]["data"]

    spans = trace["spans"]
    assert len(spans) == 10
    assert {span["op"] for span in spans} >= {"backend.yml", "acceptance.yml"}
    assert all(
        span["parent_span_id"] == trace["contexts"]["trace"]["span_id"]
        for span in spans
    )
    assert all(
        span["trace_id"] == trace["contexts"]["trace"]["trace_id"] for span in spans
    )


def test_commit_trace_id_is_stable(workflow_run, commit_runs):
    first = _generate_commit_trace(workflow_run, commit_runs)
    second = _generate_commit_trace(workflow_run, commit_runs)
    assert first["contexts"]["trace"]["trace_id"] == (
        second["contexts"]["trace"]["trace_id"]
    )


def test_only_the_last_run_to_complete_sends_the_trace(commit_runs):
    acceptance = _run(commit_runs, ACCEPTANCE_RUN_ID)
    assert _generate_commit_trace(acceptance, commit_runs) is None


def test_no_trace_while_a_run_is_in_progress(workflow_run, commit_runs):
    acceptance = _run(commit_runs, ACCEPTANCE_RUN_ID)
    acceptance["status"] = "in_progress"
    acceptance["conclusion"] = None
    assert _generate_commit_trace(workflow_run, commit_runs) is None


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "timed_out"])
def test_no_trace_when_a_run_did_not_pass(workflow_run, commit_runs, conclusion):
    _run(commit_runs, ACCEPTANCE_RUN_ID)["conclusion"] = conclusion
    assert _generate_commit_trace(workflow_run, commit_runs) is None


def test_skipped_runs_do_not_block_green(workflow_run, commit_runs):
    _run(commit_runs, ACCEPTANCE_RUN_ID)["conclusion"] = "skipped"
    assert _generate_commit_trace(workflow_run, commit_runs)


def test_rerun_turning_the_commit_green(commit_runs):
    acceptance = _run(commit_runs, ACCEPTANCE_RUN_ID)
    acceptance["run_attempt"] = 2
    acceptance["run_started_at"] = "2026-10-13T21:50:00Z"
    acceptance["updated_at"] = "2026-10-13T22:15:00Z"

    trace = _generate_commit_trace(copy.deepcopy(acceptance), commit_runs)

    # The wait before the re-run doesn't count, only the re-run itself
    assert trace["start_timestamp"] == "2026-10-13T21:50:00Z"
    assert trace["timestamp"] == "2026-10-13T22:15:00Z"
    assert trace["tags"]["rerun"] == "true"
    assert trace["tags"]["slowest_workflow"] == "acceptance.yml"


def test_only_the_latest_run_of_a_workflow_counts(workflow_run, commit_runs):
    # backend.yml got re-triggered days later, and that run is still going
    newer = copy.deepcopy(workflow_run)
    newer.update(
        id=BACKEND_RUN_ID + 1,
        status="in_progress",
        conclusion=None,
        run_started_at="2026-10-16T09:00:00Z",
        updated_at="2026-10-16T09:01:00Z",
    )
    commit_runs["workflow_runs"].append(newer)
    assert _generate_commit_trace(workflow_run, commit_runs) is None

    newer.update(
        status="completed", conclusion="success", updated_at="2026-10-16T09:12:00Z"
    )
    trace = _generate_commit_trace(newer, commit_runs)
    assert trace["tags"]["workflow_runs"] == 10
    assert trace["tags"]["slowest_workflow"] == "backend.yml"
    assert trace["start_timestamp"] == "2026-10-16T09:00:00Z"
    assert trace["timestamp"] == "2026-10-16T09:12:00Z"


def test_commit_workflows_limit_which_runs_count(workflow_run, commit_runs):
    # A failing workflow that doesn't gate the commit
    _run(commit_runs, 38468300618)["conclusion"] = "failure"
    assert _generate_commit_trace(workflow_run, commit_runs) is None

    trace = _generate_commit_trace(
        workflow_run, commit_runs, frozenset({"backend.yml", "acceptance.yml"})
    )
    assert trace["tags"]["workflow_runs"] == 2
    assert {span["op"] for span in trace["spans"]} == {"backend.yml", "acceptance.yml"}


def test_too_many_runs_for_one_page(workflow_run, commit_runs):
    commit_runs["total_count"] = 101
    assert _generate_commit_trace(workflow_run, commit_runs) is None


def test_run_missing_from_list(workflow_run, commit_runs):
    commit_runs["workflow_runs"] = [
        run for run in commit_runs["workflow_runs"] if run["id"] != BACKEND_RUN_ID
    ]
    assert _generate_commit_trace(workflow_run, commit_runs) is None


def test_pull_request_commit(workflow_run, commit_runs):
    workflow_run["event"] = "pull_request"
    workflow_run["head_branch"] = "my-feature"
    workflow_run["pull_requests"].append(
        {
            "number": 101,
            "base": {
                "ref": "master",
                "repo": {"url": "https://api.github.com/repos/getsentry/sentry"},
            },
        }
    )

    trace = _generate_commit_trace(workflow_run, commit_runs)

    assert trace["tags"]["event"] == "pull_request"
    assert trace["tags"]["pull_request"] == 101
    assert trace["tags"]["base_branch"] == "master"
    assert (
        trace["contexts"]["trace"]["data"]["pr"]
        == "https://github.com/getsentry/sentry/pull/101"
    )


@responses.activate
def test_send_commit_trace(workflow_run, commit_runs):
    responses.get(_commit_runs_url(workflow_run), json=commit_runs)
    responses.post(ENVELOPE_URL)

    resp = GithubClient(dsn=DSN, token=TOKEN).send_commit_trace(workflow_run)

    assert resp.status_code == 200
    responses.assert_call_count(ENVELOPE_URL, 1)


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "skipped"])
@responses.activate
def test_unsuccessful_run_makes_no_api_calls(workflow_run, conclusion):
    workflow_run["conclusion"] = conclusion
    assert GithubClient(dsn=DSN, token=TOKEN).send_commit_trace(workflow_run) is None
    assert len(responses.calls) == 0


@responses.activate
def test_run_outside_commit_workflows_makes_no_api_calls(workflow_run):
    client = GithubClient(dsn=DSN, token=TOKEN)
    assert client.send_commit_trace(workflow_run, frozenset({"frontend.yml"})) is None
    assert len(responses.calls) == 0


def test_workflow_run_events_are_off_by_default(monkeypatch, webhook_payload):
    monkeypatch.delenv("COMMIT_TRACES_ENABLED", raising=False)
    reason, http_code = WebAppHandler().handle_event(
        data=webhook_payload, headers={"X-GitHub-Event": "workflow_run"}
    )
    assert reason == "Commit traces are not enabled."
    assert http_code == 200


@responses.activate
def test_unsuccessful_workflow_run_event_makes_no_api_calls(
    monkeypatch, webhook_payload
):
    monkeypatch.setenv("COMMIT_TRACES_ENABLED", "true")
    webhook_payload["workflow_run"]["conclusion"] = "failure"
    reason, http_code = WebAppHandler().handle_event(
        data=webhook_payload, headers={"X-GitHub-Event": "workflow_run"}
    )
    assert reason == "Only successful workflow runs can turn a commit green."
    assert http_code == 200
    assert len(responses.calls) == 0
