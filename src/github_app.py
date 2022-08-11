"""
This module contains the logic to support running the app as a Github App
"""
from __future__ import annotations

import contextlib
import time
from typing import Generator

import jwt
import requests


class GithubAppToken:
    def __init__(self, private_key, app_id) -> None:
        self.headers = self.get_authentication_header(private_key, app_id)

    # From docs: Installation access tokens have the permissions
    # configured by the GitHub App and expire after one hour.
    @contextlib.contextmanager
    def get_token(self, installation_id: str) -> Generator[str, None, None]:
        req = requests.post(
            url=f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers=self.headers,
        )
        req.raise_for_status()
        resp = req.json()
        try:
            # This token expires in an hour
            yield resp["token"]
        finally:
            requests.delete(
                "https://api.github.com/installation/token",
                headers={"Authorization": f"token {resp['token']}"},
            )

    def get_jwt_token(self, private_key, app_id):
        payload = {
            # issued at time, 60 seconds in the past to allow for clock drift
            "iat": int(time.time()) - 60,
            # JWT expiration time (5 minutes maximum)
            "exp": int(time.time()) + 5 * 60,
            # GitHub App's identifier
            "iss": app_id,
        }
        return jwt.encode(payload, private_key, algorithm="RS256")

    def get_authentication_header(self, private_key, app_id):
        jwt_token = self.get_jwt_token(private_key, app_id)
        return {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"Bearer {jwt_token}",
        }
