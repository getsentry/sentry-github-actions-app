from __future__ import annotations

from unittest.mock import Mock
from unittest.mock import patch

import pytest
import requests

from src.github_app import GithubAppToken
from src.github_app import TOKEN_REVOKE_TIMEOUT_SECONDS


def _token_response(token: str = "temp-token") -> Mock:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"token": token}
    return response


@patch.object(
    GithubAppToken,
    "get_authentication_header",
    return_value={"Accept": "application/vnd.github.v3+json", "Authorization": "Bearer test"},
)
@patch("src.github_app.requests.delete")
@patch("src.github_app.requests.post")
def test_get_token_revokes_token_with_timeout(
    mock_post, mock_delete, _mock_get_authentication_header
):
    mock_post.return_value = _token_response()
    app_token = GithubAppToken(private_key="unused", app_id="123")

    with app_token.get_token(installation_id=1) as token:
        assert token == "temp-token"

    mock_delete.assert_called_once_with(
        "https://api.github.com/installation/token",
        headers={"Authorization": "token temp-token"},
        timeout=TOKEN_REVOKE_TIMEOUT_SECONDS,
    )


@patch.object(
    GithubAppToken,
    "get_authentication_header",
    return_value={"Accept": "application/vnd.github.v3+json", "Authorization": "Bearer test"},
)
@patch("src.github_app.requests.delete")
@patch("src.github_app.requests.post")
def test_get_token_ignores_revoke_timeout(
    mock_post, mock_delete, _mock_get_authentication_header
):
    mock_post.return_value = _token_response()
    mock_delete.side_effect = requests.ConnectTimeout("timed out")
    app_token = GithubAppToken(private_key="unused", app_id="123")

    with app_token.get_token(installation_id=1) as token:
        assert token == "temp-token"


@patch.object(
    GithubAppToken,
    "get_authentication_header",
    return_value={"Accept": "application/vnd.github.v3+json", "Authorization": "Bearer test"},
)
@patch("src.github_app.requests.delete")
@patch("src.github_app.requests.post")
def test_get_token_does_not_mask_inner_exception_when_revoke_fails(
    mock_post, mock_delete, _mock_get_authentication_header
):
    mock_post.return_value = _token_response()
    mock_delete.side_effect = requests.ConnectTimeout("timed out")
    app_token = GithubAppToken(private_key="unused", app_id="123")

    with pytest.raises(RuntimeError, match="original failure"):
        with app_token.get_token(installation_id=1):
            raise RuntimeError("original failure")
