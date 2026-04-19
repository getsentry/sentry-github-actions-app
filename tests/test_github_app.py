from __future__ import annotations

from unittest.mock import Mock
from unittest.mock import patch

import pytest
import requests

from src.github_app import GithubAppToken


@patch.object(GithubAppToken, "get_authentication_header", return_value={})
@patch("src.github_app.requests.delete")
@patch("src.github_app.time.sleep")
@patch("src.github_app.requests.post")
def test_get_token_retries_connect_timeout_then_succeeds(
    mock_post,
    mock_sleep,
    mock_delete,
    _mock_headers,
):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"token": "temporary-token"}
    mock_post.side_effect = [requests.exceptions.ConnectTimeout(), response]

    token_provider = GithubAppToken(private_key="irrelevant", app_id=123)

    with token_provider.get_token(installation_id=42) as token:
        assert token == "temporary-token"

    assert mock_post.call_count == 2
    first_call = mock_post.call_args_list[0]
    second_call = mock_post.call_args_list[1]
    assert first_call.kwargs["timeout"] == GithubAppToken.TOKEN_REQUEST_TIMEOUT_SECONDS
    assert second_call.kwargs["timeout"] == GithubAppToken.TOKEN_REQUEST_TIMEOUT_SECONDS
    assert first_call.kwargs["url"].endswith("/42/access_tokens")
    assert second_call.kwargs["url"].endswith("/42/access_tokens")
    mock_sleep.assert_called_once_with(1)
    mock_delete.assert_called_once()
    assert (
        mock_delete.call_args.kwargs["timeout"]
        == GithubAppToken.TOKEN_REQUEST_TIMEOUT_SECONDS
    )


@patch.object(GithubAppToken, "get_authentication_header", return_value={})
@patch("src.github_app.requests.delete")
@patch("src.github_app.time.sleep")
@patch("src.github_app.requests.post")
def test_get_token_raises_after_repeated_connect_timeouts(
    mock_post,
    mock_sleep,
    mock_delete,
    _mock_headers,
):
    mock_post.side_effect = [requests.exceptions.ConnectTimeout()] * 3
    token_provider = GithubAppToken(private_key="irrelevant", app_id=123)

    with pytest.raises(requests.exceptions.ConnectTimeout):
        with token_provider.get_token(installation_id=42):
            pass

    assert mock_post.call_count == GithubAppToken.TOKEN_REQUEST_MAX_ATTEMPTS
    mock_sleep.assert_any_call(1)
    mock_sleep.assert_any_call(2)
    assert mock_sleep.call_count == 2
    mock_delete.assert_not_called()


@patch.object(GithubAppToken, "get_authentication_header", return_value={})
@patch("src.github_app.requests.delete")
@patch("src.github_app.requests.post")
def test_get_token_ignores_delete_errors(
    mock_post,
    mock_delete,
    _mock_headers,
):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"token": "temporary-token"}
    mock_post.return_value = response
    mock_delete.side_effect = requests.exceptions.Timeout()

    token_provider = GithubAppToken(private_key="irrelevant", app_id=123)

    with token_provider.get_token(installation_id=42) as token:
        assert token == "temporary-token"

    mock_delete.assert_called_once()
