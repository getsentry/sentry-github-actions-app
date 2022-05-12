import os

import pytest
from src.handle_event import handle_event

# XXX: Fix this
os.environ["SENTRY_GITHUB_DSN"] = "https://foo@random.ingest.sentry.io/bar"


def test_invalid_header():
    with pytest.raises(KeyError):
        handle_event(data={}, headers={})


# XXX: These tests could be covered with a JSON schema
def test_invalid_github_event():
    reason, http_code = handle_event(
        data={}, headers={"X-GitHub-Event": "not_a_workflow_job"}
    )
    assert reason == "Event not supported."
    assert http_code == 200


def test_missing_action_key():
    with pytest.raises(KeyError):
        handle_event(
            data={"bad_key": "irrelevant"},
            headers={"X-GitHub-Event": "workflow_job"},
        )


def test_not_completed_workflow():
    reason, http_code = handle_event(
        data={"action": "not_completed"},
        headers={"X-GitHub-Event": "workflow_job"},
    )
    assert reason == "We cannot do anything with this workflow state."
    assert http_code == 200


def test_missing_workflow_job():
    with pytest.raises(KeyError):
        handle_event(
            data={"action": "completed"},
            headers={"X-GitHub-Event": "workflow_job"},
        )


# "Set SENTRY_GITHUB_SDN in order to send envelopes."
def test_no_dsn_is_set():
    with pytest.raises(KeyError):
        handle_event(
            data={"action": "completed", "workflow_job": {}},
            headers={"X-GitHub-Event": "workflow_job"},
        )
