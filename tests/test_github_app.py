from __future__ import annotations

from unittest.mock import patch

import pytest
import requests
import responses

from src.github_app import GithubAppToken

CREATE_TOKEN_URL = "https://api.github.com/app/installations/123/access_tokens"
REVOKE_TOKEN_URL = "https://api.github.com/installation/token"


def make_github_app_token():
    with patch.object(
        GithubAppToken,
        "get_authentication_header",
        return_value={"Authorization": "Bearer jwt"},
    ):
        return GithubAppToken(private_key="irrelevant", app_id=1)


@responses.activate
def test_token_revocation_failure_does_not_mask_handler_error():
    responses.post(CREATE_TOKEN_URL, json={"token": "installation-token"}, status=201)
    responses.delete(REVOKE_TOKEN_URL, body=requests.ConnectionError("reset"))
    responses.delete(REVOKE_TOKEN_URL, body=requests.ConnectionError("reset"))

    with pytest.raises(RuntimeError, match="handler failed"):
        with make_github_app_token().get_token(123) as token:
            assert token == "installation-token"
            raise RuntimeError("handler failed")

    assert len(responses.calls) == 3
    assert responses.calls[1].request.headers["Authorization"] == (
        "token installation-token"
    )
