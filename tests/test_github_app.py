from __future__ import annotations

from unittest.mock import Mock
from unittest.mock import call
from unittest.mock import patch

import pytest
import requests

from src.github_app import GithubAppToken
from src.github_app import TOKEN_REQUEST_BACKOFF_SECONDS
from src.github_app import TOKEN_REQUEST_MAX_ATTEMPTS
from src.github_app import TOKEN_REQUEST_TIMEOUT_SECONDS


def _build_token_manager() -> GithubAppToken:
    with patch.object(GithubAppToken, "get_authentication_header", return_value={}):
        return GithubAppToken(private_key="irrelevant", app_id="1")


def test_get_token_retries_ssl_errors_and_returns_token():
    token_manager = _build_token_manager()
    success_response = Mock()
    success_response.raise_for_status.return_value = None
    success_response.json.return_value = {"token": "test-token"}

    with (
        patch(
            "src.github_app.requests.post",
            side_effect=[requests.exceptions.SSLError("tls"), success_response],
        ) as mock_post,
        patch("src.github_app.requests.delete") as mock_delete,
        patch("src.github_app.time.sleep") as mock_sleep,
    ):
        with token_manager.get_token(123) as token:
            assert token == "test-token"

    assert mock_post.call_count == 2
    mock_sleep.assert_called_once_with(TOKEN_REQUEST_BACKOFF_SECONDS)
    mock_delete.assert_called_once_with(
        "https://api.github.com/installation/token",
        headers={"Authorization": "token test-token"},
        timeout=TOKEN_REQUEST_TIMEOUT_SECONDS,
    )


def test_get_token_raises_after_max_transient_failures():
    token_manager = _build_token_manager()

    with (
        patch(
            "src.github_app.requests.post",
            side_effect=requests.exceptions.Timeout("slow network"),
        ) as mock_post,
        patch("src.github_app.requests.delete") as mock_delete,
        patch("src.github_app.time.sleep") as mock_sleep,
    ):
        with pytest.raises(requests.exceptions.Timeout):
            with token_manager.get_token(123):
                pass

    assert mock_post.call_count == TOKEN_REQUEST_MAX_ATTEMPTS
    assert mock_sleep.call_args_list == [
        call(TOKEN_REQUEST_BACKOFF_SECONDS),
        call(TOKEN_REQUEST_BACKOFF_SECONDS * 2),
    ]
    mock_delete.assert_not_called()


def test_get_token_does_not_retry_http_error():
    token_manager = _build_token_manager()
    failed_response = Mock()
    failed_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500")

    with (
        patch("src.github_app.requests.post", return_value=failed_response) as mock_post,
        patch("src.github_app.requests.delete") as mock_delete,
        patch("src.github_app.time.sleep") as mock_sleep,
    ):
        with pytest.raises(requests.exceptions.HTTPError):
            with token_manager.get_token(123):
                pass

    assert mock_post.call_count == 1
    mock_sleep.assert_not_called()
    mock_delete.assert_not_called()
