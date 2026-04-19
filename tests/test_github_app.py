from __future__ import annotations

from unittest.mock import Mock
from unittest.mock import patch

import requests

from src.github_app import GithubAppToken


@patch("src.github_app.requests.post")
@patch("src.github_app.requests.delete")
@patch.object(GithubAppToken, "get_authentication_header", return_value={})
def test_get_token_ignores_revoke_timeout(
    _mock_auth_header,
    mock_delete,
    mock_post,
    caplog,
):
    post_response = Mock()
    post_response.raise_for_status.return_value = None
    post_response.json.return_value = {"token": "generated-token"}
    mock_post.return_value = post_response
    mock_delete.side_effect = requests.ConnectTimeout()

    token_manager = GithubAppToken(private_key="irrelevant", app_id="irrelevant")
    caplog.set_level("WARNING", logger="src.github_app")

    with token_manager.get_token(1234) as token:
        assert token == "generated-token"

    mock_delete.assert_called_once_with(
        "https://api.github.com/installation/token",
        headers={"Authorization": "token generated-token"},
        timeout=10,
    )
    assert "Failed to revoke GitHub installation token. Continuing." in caplog.text


@patch("src.github_app.requests.post")
@patch("src.github_app.requests.delete")
@patch.object(GithubAppToken, "get_authentication_header", return_value={})
def test_get_token_ignores_revoke_http_error(
    _mock_auth_header,
    mock_delete,
    mock_post,
    caplog,
):
    post_response = Mock()
    post_response.raise_for_status.return_value = None
    post_response.json.return_value = {"token": "generated-token"}
    mock_post.return_value = post_response

    revoke_response = Mock()
    revoke_response.raise_for_status.side_effect = requests.HTTPError()
    mock_delete.return_value = revoke_response

    token_manager = GithubAppToken(private_key="irrelevant", app_id="irrelevant")
    caplog.set_level("WARNING", logger="src.github_app")

    with token_manager.get_token(1234) as token:
        assert token == "generated-token"

    revoke_response.raise_for_status.assert_called_once()
    assert "Failed to revoke GitHub installation token. Continuing." in caplog.text
