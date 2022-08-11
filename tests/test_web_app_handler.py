from __future__ import annotations

import json
from unittest import mock

import pytest

from src.web_app_handler import WebAppHandler

valid_signature = "ad21e4e6a981bd1656fcd56ed0039b9ab4f292a997517e26fe77aab63920a9ad"


def test_invalid_header():
    handler = WebAppHandler()
    # This is missing X-GitHub-Event in the headers
    with pytest.raises(KeyError) as excinfo:
        handler.handle_event(data={}, headers={})
    (msg,) = excinfo.value.args
    assert msg == "X-GitHub-Event"


# XXX: These tests could be covered with a JSON schema
def test_invalid_github_event():
    handler = WebAppHandler()
    # This has an invalid X-GitHub-Event value
    reason, http_code = handler.handle_event(
        data={},
        headers={"X-GitHub-Event": "not_a_workflow_job"},
    )
    assert reason == "Event not supported."
    assert http_code == 200


def test_missing_action_key():
    handler = WebAppHandler()
    # This payload is missing the action key
    with pytest.raises(KeyError) as excinfo:
        handler.handle_event(
            data={"bad_key": "irrelevant"},
            headers={"X-GitHub-Event": "workflow_job"},
        )
    (msg,) = excinfo.value.args
    assert msg == "action"


def test_not_completed_workflow():
    handler = WebAppHandler()
    # This payload has an an action state we cannot process
    reason, http_code = handler.handle_event(
        data={"action": "not_completed"},
        headers={"X-GitHub-Event": "workflow_job"},
    )
    assert reason == "We cannot do anything with this workflow state."
    assert http_code == 200


def test_missing_workflow_job(monkeypatch):
    monkeypatch.delenv("GH_APP_ID", raising=False)
    handler = WebAppHandler()
    # This tries to send a trace but we're missing the workflow_job key
    with pytest.raises(KeyError) as excinfo:
        handler.handle_event(
            data={"action": "completed"},
            headers={"X-GitHub-Event": "workflow_job"},
        )
    (msg,) = excinfo.value.args
    assert msg == "workflow_job"


def test_valid_signature_no_secret(monkeypatch):
    monkeypatch.delenv("GH_WEBHOOK_SECRET", raising=False)
    handler = WebAppHandler()
    assert handler.valid_signature(body={}, headers={}) == True


def test_valid_signature(monkeypatch, webhook_event):
    monkeypatch.setenv("GH_WEBHOOK_SECRET", "fake_secret")
    handler = WebAppHandler()
    assert (
        handler.valid_signature(
            body=json.dumps(webhook_event["payload"]).encode(),
            headers={"X-Hub-Signature-256": f"sha256={valid_signature}"},
        )
        == True
    )


def test_invalid_signature(monkeypatch, webhook_event):
    monkeypatch.setenv("GH_WEBHOOK_SECRET", "mistyped_secret")
    handler = WebAppHandler()
    # This is unit testing that the function works as expected
    assert (
        handler.valid_signature(
            body=json.dumps(webhook_event["payload"]).encode(),
            headers={"X-Hub-Signature-256": f"sha256={valid_signature}"},
        )
        == False
    )


def test_handle_event_with_secret(monkeypatch, webhook_event):
    monkeypatch.setenv("GH_WEBHOOK_SECRET", "fake_secret")
    handler = WebAppHandler(dry_run=True)
    reason, http_code = handler.handle_event(
        data=webhook_event["payload"],
        headers=webhook_event["headers"],
    )
    assert reason == "OK"
    assert http_code == 200
