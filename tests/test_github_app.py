from __future__ import annotations

import requests
import responses

from src.github_app import GithubAppToken


@responses.activate
def test_token_revocation_failure_does_not_mask_successful_work():
    token = "synthetic-token"
    installation_id = 1234
    client = object.__new__(GithubAppToken)
    client.headers = {"Authorization": "Bearer synthetic-jwt"}

    responses.post(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        json={"token": token},
        status=201,
    )
    responses.delete(
        "https://api.github.com/installation/token",
        body=requests.ConnectionError("connection closed during cleanup"),
    )

    with client.get_token(installation_id) as installation_token:
        assert installation_token == token

    assert len(responses.calls) == 2
