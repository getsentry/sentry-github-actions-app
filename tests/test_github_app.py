from __future__ import annotations

from unittest.mock import Mock

import pytest
import requests

from src.github_app import GITHUB_API_TIMEOUT, GithubAppToken


class DummyResponse:
    def __init__(self, payload=None, error=None) -> None:
        self.payload = payload or {}
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self.payload


@pytest.fixture
def github_app_token():
    token = GithubAppToken.__new__(GithubAppToken)
    token.headers = {"Authorization": "Bearer jwt"}
    return token


def test_get_token_retries_transient_token_creation_errors(
    github_app_token,
    monkeypatch,
):
    calls = []
    sleep = Mock()
    monkeypatch.setattr("src.github_app.time.sleep", sleep)

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        post_attempts = len([call for call in calls if call[0] == "POST"])
        if method == "POST" and post_attempts == 1:
            raise requests.exceptions.ConnectTimeout("connect timeout")
        return DummyResponse({"token": "github-token"})

    monkeypatch.setattr("src.github_app.requests.request", request)

    with github_app_token.get_token(42) as token:
        assert token == "github-token"

    post_calls = [call for call in calls if call[0] == "POST"]
    assert len(post_calls) == 2
    assert calls[-1][0] == "DELETE"
    assert all(call[2]["timeout"] == GITHUB_API_TIMEOUT for call in calls)
    sleep.assert_called_once_with(1)


def test_get_token_does_not_retry_http_status_errors(github_app_token, monkeypatch):
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return DummyResponse(error=requests.HTTPError("server error"))

    monkeypatch.setattr("src.github_app.requests.request", request)

    with pytest.raises(requests.HTTPError):
        with github_app_token.get_token(42):
            pass

    assert len(calls) == 1
