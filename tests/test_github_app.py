from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from src.github_app import GithubAppToken


def _build_response(token: str) -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"token": token}
    return response


@patch.object(GithubAppToken, "get_authentication_header", return_value={})
@patch("src.github_app.requests.delete")
@patch("src.github_app.requests.post")
def test_get_token_revokes_installation_token(
    mock_post: MagicMock,
    mock_delete: MagicMock,
    _mock_get_authentication_header: MagicMock,
):
    mock_post.return_value = _build_response("installation-token")
    token_manager = GithubAppToken(private_key="unused", app_id="123")

    with token_manager.get_token(installation_id=42) as token:
        assert token == "installation-token"

    mock_delete.assert_called_once_with(
        "https://api.github.com/installation/token",
        headers={"Authorization": "token installation-token"},
    )


@patch.object(GithubAppToken, "get_authentication_header", return_value={})
@patch("src.github_app.requests.delete")
@patch("src.github_app.requests.post")
def test_cleanup_timeout_does_not_mask_primary_exception(
    mock_post: MagicMock,
    mock_delete: MagicMock,
    _mock_get_authentication_header: MagicMock,
):
    mock_post.return_value = _build_response("installation-token")
    mock_delete.side_effect = requests.ConnectTimeout("cleanup timeout")
    token_manager = GithubAppToken(private_key="unused", app_id="123")

    with pytest.raises(requests.ConnectTimeout, match="primary timeout"):
        with token_manager.get_token(installation_id=42):
            raise requests.ConnectTimeout("primary timeout")
