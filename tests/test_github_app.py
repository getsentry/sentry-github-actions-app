from __future__ import annotations

from unittest.mock import Mock
from unittest.mock import patch

import pytest
import requests

from src.github_app import GithubAppToken


def _new_client():
    client = GithubAppToken.__new__(GithubAppToken)
    client.headers = {"Authorization": "Bearer jwt-token"}
    return client


def test_get_token_revokes_installation_token():
    client = _new_client()
    token_response = Mock()
    token_response.raise_for_status.return_value = None
    token_response.json.return_value = {"token": "installation-token"}

    with patch("src.github_app.requests.post", return_value=token_response) as post_mock:
        with patch("src.github_app.requests.delete") as delete_mock:
            with client.get_token(12345) as token:
                assert token == "installation-token"

    post_mock.assert_called_once_with(
        url="https://api.github.com/app/installations/12345/access_tokens",
        headers=client.headers,
    )
    delete_mock.assert_called_once_with(
        "https://api.github.com/installation/token",
        headers={"Authorization": "token installation-token"},
        timeout=5,
    )


def test_get_token_cleanup_network_error_is_non_fatal():
    client = _new_client()
    token_response = Mock()
    token_response.raise_for_status.return_value = None
    token_response.json.return_value = {"token": "installation-token"}

    with patch("src.github_app.requests.post", return_value=token_response):
        with patch(
            "src.github_app.requests.delete",
            side_effect=requests.ConnectionError("cleanup failed"),
        ):
            with patch("src.github_app.logger.warning") as warning_mock:
                with client.get_token(12345) as token:
                    assert token == "installation-token"

    warning_mock.assert_called_once()


def test_get_token_cleanup_error_does_not_mask_inner_exception():
    client = _new_client()
    token_response = Mock()
    token_response.raise_for_status.return_value = None
    token_response.json.return_value = {"token": "installation-token"}

    with patch("src.github_app.requests.post", return_value=token_response):
        with patch(
            "src.github_app.requests.delete",
            side_effect=requests.ConnectionError("cleanup failed"),
        ):
            with pytest.raises(ValueError, match="primary failure"):
                with client.get_token(12345):
                    raise ValueError("primary failure")
