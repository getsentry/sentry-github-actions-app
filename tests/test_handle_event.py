import json

import pytest

from src.event_handler import EventHandler


def test_invalid_header():
    handler = EventHandler()
    # This is missing X-GitHub-Event in the headers
    with pytest.raises(KeyError) as excinfo:
        handler.handle_event(data={}, headers={})
    (msg,) = excinfo.value.args
    assert msg == "X-GitHub-Event"


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
    with pytest.raises(KeyError) as excinfo:
        handler.handle_event(
            data={"bad_key": "irrelevant"},
            headers={"X-GitHub-Event": "workflow_job"},
        )
    (msg,) = excinfo.value.args
    assert msg == "action"


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
    with pytest.raises(KeyError) as excinfo:
        handler.handle_event(
            data={"action": "completed"},
            headers={"X-GitHub-Event": "workflow_job"},
        )
    (msg,) = excinfo.value.args
    assert msg == "workflow_job"


# "Set SENTRY_GITHUB_SDN in order to send envelopes."
def test_no_dsn_is_set():
    handler = EventHandler()
    # This tries to process a job that does not have the conclusion key
    with pytest.raises(KeyError) as excinfo:
        handler.handle_event(
            data={"action": "completed", "workflow_job": {}},
            headers={"X-GitHub-Event": "workflow_job"},
        )
    (msg,) = excinfo.value.args
    assert msg == "conclusion"


def test_valid_signature(webhook_event):
    handler = EventHandler(secret="fake_secret")
    assert (
        handler.valid_signature(
            body=json.dumps(webhook_event["payload"]).encode(),
            headers={
                "X-Hub-Signature-256": "sha256=ad21e4e6a981bd1656fcd56ed0039b9ab4f292a997517e26fe77aab63920a9ad",
            },
        )
        == True
    )


def test_invalid_signature(webhook_event):
    handler = EventHandler(secret="mistyped_secret")
    # This is unit testing that the function works as expected
    assert (
        handler.valid_signature(
            body=json.dumps(webhook_event["payload"]).encode(),
            headers={
                "X-Hub-Signature-256": "sha256=b7b02a023839f2a85b164e5732b49b939d90f42558d1cd8386e188f20648b0e8",
            },
        )
        == False
    )


def test_handle_event_with_secret(webhook_event):
    handler = EventHandler(secret="fake_secret", dry_run=True)
    reason, http_code = handler.handle_event(
        data=webhook_event["payload"],
        headers=webhook_event["headers"],
    )
    assert reason == "OK"
    assert http_code == 200
