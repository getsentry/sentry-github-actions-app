import pytest
from src.event_handler import EventHandler


def test_invalid_header():
    handler = EventHandler()
    # This is missing X-GitHub-Event in the headers
    with pytest.raises(KeyError):
        handler.handle_event(data={}, headers={})


# XXX: These tests could be covered with a JSON schema
def test_invalid_github_event():
    handler = EventHandler()
    # This has an invalid X-GitHub-Event value
    reason, http_code = handler.handle_event(
        data={}, headers={"X-GitHub-Event": "not_a_workflow_job"}
    )
    assert reason == "Event not supported."
    assert http_code == 200


def test_missing_action_key():
    handler = EventHandler()
    # This payload is missing the action key
    with pytest.raises(KeyError):
        handler.handle_event(
            data={"bad_key": "irrelevant"},
            headers={"X-GitHub-Event": "workflow_job"},
        )


def test_not_completed_workflow():
    handler = EventHandler()
    # This payload has an an action state we cannot process
    reason, http_code = handler.handle_event(
        data={"action": "not_completed"},
        headers={"X-GitHub-Event": "workflow_job"},
    )
    assert reason == "We cannot do anything with this workflow state."
    assert http_code == 200


def test_missing_workflow_job():
    handler = EventHandler()
    # This tries to send a trace but we're missing the workflow_job key
    with pytest.raises(KeyError):
        handler.handle_event(
            data={"action": "completed"},
            headers={"X-GitHub-Event": "workflow_job"},
        )


# "Set SENTRY_GITHUB_SDN in order to send envelopes."
def test_no_dsn_is_set():
    handler = EventHandler()
    # This tries to process a job that does not have the conclusion key
    with pytest.raises(KeyError):
        handler.handle_event(
            data={"action": "completed", "workflow_job": {}},
            headers={"X-GitHub-Event": "workflow_job"},
        )
