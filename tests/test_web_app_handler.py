from __future__ import annotations

import base64
import json
from unittest import mock

import pytest
import responses
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.web_app_handler import WebAppHandler

valid_signature = "d9259f51d3b64e7fe0cbe09d9b08b8ee763170d3521fecc35fd8b453be8cf6a5"


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


@pytest.fixture
def gh_app_env(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.setenv("GH_APP_ID", "1")
    monkeypatch.setenv("GH_APP_PRIVATE_KEY", base64.b64encode(pem).decode())


@responses.activate
def test_skipped_job_makes_no_api_calls(gh_app_env, skipped_workflow):
    handler = WebAppHandler()
    # Only Github App mode mints an installation token
    assert handler.config.gh_app
    reason, http_code = handler.handle_event(
        data={
            "action": "completed",
            "installation": {"id": 1},
            "repository": {"owner": {"login": "getsentry"}},
            "workflow_job": skipped_workflow,
        },
        headers={"X-GitHub-Event": "workflow_job"},
    )
    assert reason == "Skipped jobs are not traced."
    assert http_code == 200
    assert len(responses.calls) == 0


@pytest.mark.skip(reason="Not so important")
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
