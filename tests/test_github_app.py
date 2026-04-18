from __future__ import annotations

from unittest.mock import Mock
from unittest.mock import patch

import pytest
import requests

from src.github_app import GithubAppToken


def _new_token_manager():
    manager = GithubAppToken.__new__(GithubAppToken)
    manager.headers = {"Authorization": "Bearer fake-jwt"}
    return manager


@patch("src.github_app.requests.delete")
@patch("src.github_app.requests.post")
def test_get_token_returns_token_when_cleanup_succeeds(mock_post, mock_delete):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"token": "installation-token"}
    mock_post.return_value = response

    manager = _new_token_manager()
    with manager.get_token(123) as token:
        assert token == "installation-token"

    mock_delete.assert_called_once_with(
        "https://api.github.com/installation/token",
        headers={"Authorization": "token installation-token"},
    )


@patch("src.github_app.requests.delete")
@patch("src.github_app.requests.post")
def test_get_token_does_not_mask_original_error_when_cleanup_fails(
    mock_post,
    mock_delete,
):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"token": "installation-token"}
    mock_post.return_value = response
    mock_delete.side_effect = requests.ConnectionError("cleanup network failure")

    manager = _new_token_manager()
    with pytest.raises(RuntimeError, match="original failure"):
        with manager.get_token(123):
            raise RuntimeError("original failure")
