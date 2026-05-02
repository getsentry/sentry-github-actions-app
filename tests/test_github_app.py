from __future__ import annotations

import pytest
import requests

from src.github_app import GithubAppToken


def test_get_token_ignores_revocation_request_failure(monkeypatch):
    token = "github-token"
    app_token = GithubAppToken.__new__(GithubAppToken)
    app_token.headers = {"Authorization": "Bearer jwt-token"}

    class TokenResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"token": token}

    monkeypatch.setattr(requests, "post", lambda **kwargs: TokenResponse())

    def fail_revocation(*args, **kwargs):
        raise requests.ConnectionError("remote disconnected")

    monkeypatch.setattr(requests, "delete", fail_revocation)

    with app_token.get_token(123) as returned_token:
        assert returned_token == token


def test_get_token_raises_when_token_request_fails(monkeypatch):
    app_token = GithubAppToken.__new__(GithubAppToken)
    app_token.headers = {"Authorization": "Bearer jwt-token"}

    class TokenResponse:
        def raise_for_status(self):
            raise requests.HTTPError("server error")

    monkeypatch.setattr(requests, "post", lambda **kwargs: TokenResponse())

    with pytest.raises(requests.HTTPError):
        with app_token.get_token(123):
            pass
