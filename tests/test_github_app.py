from __future__ import annotations

import logging
from unittest.mock import Mock, patch

import pytest
import requests

from src.github_app import (
    GITHUB_API_MAX_ATTEMPTS,
    GITHUB_API_TIMEOUT_SECONDS,
    GithubAppToken,
)


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body

    def raise_for_status(self):
        return None


def make_github_app_token():
    github_app_token = GithubAppToken.__new__(GithubAppToken)
    github_app_token.headers = {"Authorization": "Bearer app-token"}
    return github_app_token


@patch("src.github_app.time.sleep")
@patch("src.github_app.requests.delete")
@patch("src.github_app.requests.post")
def test_get_token_retries_installation_token_creation(
    mock_post,
    mock_delete,
    mock_sleep,
):
    mock_post.side_effect = [
        requests.ConnectTimeout("connection timed out"),
        FakeResponse({"token": "installation-token"}),
    ]
    mock_delete.return_value = FakeResponse({})

    with make_github_app_token().get_token(123) as token:
        assert token == "installation-token"

    assert mock_post.call_count == 2
    for call in mock_post.call_args_list:
        assert call.kwargs["timeout"] == GITHUB_API_TIMEOUT_SECONDS
    mock_sleep.assert_called_once_with(1)


@patch("src.github_app.time.sleep")
@patch("src.github_app.requests.delete")
@patch("src.github_app.requests.post")
def test_get_token_logs_and_swallows_revocation_timeout(
    mock_post,
    mock_delete,
    mock_sleep,
    caplog,
):
    mock_post.return_value = FakeResponse({"token": "installation-token"})
    mock_delete.side_effect = requests.ConnectTimeout("connection timed out")

    with caplog.at_level(logging.WARNING):
        with make_github_app_token().get_token(123) as token:
            assert token == "installation-token"

    assert mock_delete.call_count == GITHUB_API_MAX_ATTEMPTS
    for call in mock_delete.call_args_list:
        assert call.kwargs["timeout"] == GITHUB_API_TIMEOUT_SECONDS
    assert mock_sleep.call_count == GITHUB_API_MAX_ATTEMPTS - 1
    assert "Failed to revoke GitHub installation token" in caplog.text


@patch("src.github_app.time.sleep")
@patch("src.github_app.requests.delete")
@patch("src.github_app.requests.post")
def test_get_token_preserves_context_errors_when_revocation_times_out(
    mock_post,
    mock_delete,
    mock_sleep,
):
    mock_post.return_value = FakeResponse({"token": "installation-token"})
    mock_delete.side_effect = requests.ConnectTimeout("connection timed out")

    with pytest.raises(RuntimeError, match="processing failed"):
        with make_github_app_token().get_token(123):
            raise RuntimeError("processing failed")

    assert mock_delete.call_count == GITHUB_API_MAX_ATTEMPTS
    assert mock_sleep.call_count == GITHUB_API_MAX_ATTEMPTS - 1
