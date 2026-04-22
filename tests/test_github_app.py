from __future__ import annotations

from unittest import mock

import pytest
import requests

from src.github_app import GithubAppToken


def _token_response(token: str = "temporary-token"):
    response = mock.Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"token": token}
    return response


def test_get_token_cleanup_failure_does_not_mask_primary_error():
    post_response = _token_response()

    with (
        mock.patch.object(
            GithubAppToken,
            "get_authentication_header",
            return_value={"Authorization": "Bearer test-jwt"},
        ),
        mock.patch("src.github_app.requests.post", return_value=post_response),
        mock.patch(
            "src.github_app.requests.delete",
            side_effect=requests.ConnectionError("connection reset"),
        ) as delete_mock,
    ):
        token_manager = GithubAppToken(private_key="irrelevant", app_id="123")

        with pytest.raises(RuntimeError, match="primary failure"):
            with token_manager.get_token(installation_id=42):
                raise RuntimeError("primary failure")

        delete_mock.assert_called_once_with(
            "https://api.github.com/installation/token",
            headers={"Authorization": "token temporary-token"},
        )


def test_get_token_cleanup_failure_is_best_effort_without_primary_error():
    post_response = _token_response()

    with (
        mock.patch.object(
            GithubAppToken,
            "get_authentication_header",
            return_value={"Authorization": "Bearer test-jwt"},
        ),
        mock.patch("src.github_app.requests.post", return_value=post_response),
        mock.patch(
            "src.github_app.requests.delete",
            side_effect=requests.ConnectionError("connection reset"),
        ),
    ):
        token_manager = GithubAppToken(private_key="irrelevant", app_id="123")

        with token_manager.get_token(installation_id=42) as token:
            assert token == "temporary-token"
