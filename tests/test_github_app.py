from __future__ import annotations

from unittest import mock

import pytest
import requests

from src.github_app import GithubAppToken


def _token_manager() -> GithubAppToken:
    manager = GithubAppToken.__new__(GithubAppToken)
    manager.headers = {"Authorization": "Bearer jwt"}
    return manager


def test_get_token_ignores_revoke_errors():
    token_manager = _token_manager()
    token_response = mock.Mock()
    token_response.raise_for_status.return_value = None
    token_response.json.return_value = {"token": "test-token"}

    with (
        mock.patch("src.github_app.requests.post", return_value=token_response),
        mock.patch(
            "src.github_app.requests.delete",
            side_effect=requests.ConnectionError("remote closed"),
        ) as delete_mock,
        mock.patch("src.github_app.logger.warning") as warning_mock,
    ):
        with token_manager.get_token(installation_id=1234) as token:
            assert token == "test-token"

    delete_mock.assert_called_once_with(
        "https://api.github.com/installation/token",
        headers={"Authorization": "token test-token"},
    )
    warning_mock.assert_called_once()


def test_get_token_raises_when_access_token_request_fails():
    token_manager = _token_manager()
    token_response = mock.Mock()
    token_response.raise_for_status.side_effect = requests.HTTPError("bad gateway")

    with (
        mock.patch("src.github_app.requests.post", return_value=token_response),
        mock.patch("src.github_app.requests.delete") as delete_mock,
        pytest.raises(requests.HTTPError),
    ):
        with token_manager.get_token(installation_id=1234):
            pass

    delete_mock.assert_not_called()
