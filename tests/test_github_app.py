from __future__ import annotations

from unittest.mock import Mock
from unittest.mock import patch

import requests

from src.github_app import GithubAppToken


def _new_token_manager() -> GithubAppToken:
    token_manager = GithubAppToken.__new__(GithubAppToken)
    token_manager.headers = {"Authorization": "Bearer fake-app-jwt"}
    return token_manager


@patch("src.github_app.logger.warning")
@patch("src.github_app.requests.delete")
@patch("src.github_app.requests.post")
def test_get_token_delete_error_is_best_effort(
    mock_post,
    mock_delete,
    mock_warning,
):
    mock_resp = Mock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"token": "temporary-installation-token"}
    mock_post.return_value = mock_resp
    mock_delete.side_effect = requests.exceptions.SSLError("eof during handshake")

    token_manager = _new_token_manager()
    with token_manager.get_token(12345) as token:
        assert token == "temporary-installation-token"

    mock_delete.assert_called_once_with(
        "https://api.github.com/installation/token",
        headers={"Authorization": "token temporary-installation-token"},
    )
    mock_warning.assert_called_once()


@patch("src.github_app.logger.warning")
@patch("src.github_app.requests.delete")
@patch("src.github_app.requests.post")
def test_get_token_still_revokes_when_delete_succeeds(
    mock_post,
    mock_delete,
    mock_warning,
):
    mock_resp = Mock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"token": "temporary-installation-token"}
    mock_post.return_value = mock_resp

    token_manager = _new_token_manager()
    with token_manager.get_token(12345) as token:
        assert token == "temporary-installation-token"

    mock_delete.assert_called_once_with(
        "https://api.github.com/installation/token",
        headers={"Authorization": "token temporary-installation-token"},
    )
    mock_warning.assert_not_called()
