from __future__ import annotations

from unittest.mock import patch

import pytest
import requests
import responses

from src.github_app import GithubAppToken


CREATE_TOKEN_URL = (
    "https://api.github.com/app/installations/123/access_tokens"
)
REVOKE_TOKEN_URL = "https://api.github.com/installation/token"


def github_app_token():
    app_token = object.__new__(GithubAppToken)
    app_token.headers = {}
    return app_token


def register_token_revocation_failure():
    for _ in range(3):
        responses.delete(
            REVOKE_TOKEN_URL,
            body=requests.exceptions.ConnectionError("connection reset"),
        )


@responses.activate
@patch("src.github_requests.time.sleep")
def test_token_revocation_connection_error_is_ignored(mock_sleep):
    responses.post(CREATE_TOKEN_URL, json={"token": "installation-token"}, status=201)
    register_token_revocation_failure()

    with github_app_token().get_token(123) as token:
        assert token == "installation-token"

    assert len(responses.calls) == 4


@responses.activate
@patch("src.github_requests.time.sleep")
def test_token_revocation_connection_error_does_not_mask_work_error(mock_sleep):
    responses.post(CREATE_TOKEN_URL, json={"token": "installation-token"}, status=201)
    register_token_revocation_failure()

    with pytest.raises(requests.exceptions.ConnectionError, match="work failed"):
        with github_app_token().get_token(123):
            raise requests.exceptions.ConnectionError("work failed")

    assert len(responses.calls) == 4
