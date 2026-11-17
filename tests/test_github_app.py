from __future__ import annotations

from unittest.mock import patch

import pytest
import requests
import responses

from src.github_app import GithubAppToken

ACCESS_TOKENS_URL = "https://api.github.com/app/installations/1/access_tokens"
REVOKE_URL = "https://api.github.com/installation/token"


@pytest.fixture
def app_token() -> GithubAppToken:
    with patch.object(GithubAppToken, "get_authentication_header", return_value={}):
        return GithubAppToken(private_key="unused", app_id="1")


@responses.activate
def test_failed_revoke_does_not_fail_the_request(app_token: GithubAppToken) -> None:
    responses.post(ACCESS_TOKENS_URL, json={"token": "installation_token"})
    responses.delete(REVOKE_URL, body=requests.ConnectTimeout("revoke timed out"))

    with app_token.get_token(1) as token:
        assert token == "installation_token"

    assert [call.request.method for call in responses.calls] == ["POST", "DELETE"]


@responses.activate
def test_failed_revoke_does_not_mask_the_original_error(
    app_token: GithubAppToken,
) -> None:
    responses.post(ACCESS_TOKENS_URL, json={"token": "installation_token"})
    responses.delete(REVOKE_URL, body=requests.ConnectTimeout("revoke timed out"))

    with pytest.raises(ValueError, match="original error"):
        with app_token.get_token(1):
            raise ValueError("original error")
