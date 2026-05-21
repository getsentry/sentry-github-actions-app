from __future__ import annotations

import logging

import requests

from src.github_app import GITHUB_API_TIMEOUT
from src.github_app import GithubAppToken


class FakeResponse:
    def __init__(self, payload=None, error=None):
        self.payload = payload or {}
        self.error = error

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.error:
            raise self.error


def test_get_token_revocation_timeout_is_best_effort(monkeypatch, caplog):
    delete_calls = []

    def fake_post(url, headers, timeout):
        return FakeResponse({"token": "installation-token"})

    def fake_delete(url, headers, timeout):
        delete_calls.append(
            {
                "url": url,
                "headers": headers,
                "timeout": timeout,
            }
        )
        raise requests.ConnectTimeout()

    monkeypatch.setattr("src.github_app.requests.post", fake_post)
    monkeypatch.setattr("src.github_app.requests.delete", fake_delete)

    token_client = GithubAppToken.__new__(GithubAppToken)
    token_client.headers = {"Authorization": "Bearer jwt-token"}

    caplog.set_level(logging.WARNING)
    with token_client.get_token(123) as token:
        assert token == "installation-token"

    assert delete_calls == [
        {
            "url": "https://api.github.com/installation/token",
            "headers": {"Authorization": "token installation-token"},
            "timeout": GITHUB_API_TIMEOUT,
        }
    ]
    assert "Failed to revoke GitHub installation token." in caplog.text


def test_get_token_requests_access_token_with_timeout(monkeypatch):
    post_calls = []

    def fake_post(url, headers, timeout):
        post_calls.append(
            {
                "url": url,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return FakeResponse({"token": "installation-token"})

    monkeypatch.setattr("src.github_app.requests.post", fake_post)
    monkeypatch.setattr(
        "src.github_app.requests.delete",
        lambda url, headers, timeout: FakeResponse(),
    )

    token_client = GithubAppToken.__new__(GithubAppToken)
    token_client.headers = {"Authorization": "Bearer jwt-token"}

    with token_client.get_token(123) as token:
        assert token == "installation-token"

    assert post_calls == [
        {
            "url": "https://api.github.com/app/installations/123/access_tokens",
            "headers": {"Authorization": "Bearer jwt-token"},
            "timeout": GITHUB_API_TIMEOUT,
        }
    ]
