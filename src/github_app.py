"""
This module contains the logic to support running the app as a Github App
"""
from __future__ import annotations

import contextlib
import time
from typing import Generator

import jwt
import requests

TOKEN_REQUEST_TIMEOUT_SECONDS = 10
TOKEN_REQUEST_MAX_ATTEMPTS = 3
TOKEN_REQUEST_BACKOFF_SECONDS = 1


class GithubAppToken:
    def __init__(self, private_key, app_id) -> None:
        self.headers = self.get_authentication_header(private_key, app_id)

    # From docs: Installation access tokens have the permissions
    # configured by the GitHub App and expire after one hour.
    @contextlib.contextmanager
    def get_token(self, installation_id: int) -> Generator[str, None, None]:
        resp = self._create_installation_access_token(installation_id)
        try:
            # This token expires in an hour
            yield resp["token"]
        finally:
            requests.delete(
                "https://api.github.com/installation/token",
                headers={"Authorization": f"token {resp['token']}"},
                timeout=TOKEN_REQUEST_TIMEOUT_SECONDS,
            )

    def _create_installation_access_token(self, installation_id: int) -> dict:
        for attempt in range(1, TOKEN_REQUEST_MAX_ATTEMPTS + 1):
            try:
                req = requests.post(
                    url=f"https://api.github.com/app/installations/{installation_id}/access_tokens",
                    headers=self.headers,
                    timeout=TOKEN_REQUEST_TIMEOUT_SECONDS,
                )
                req.raise_for_status()
                return req.json()
            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.SSLError,
                requests.exceptions.Timeout,
            ):
                if attempt == TOKEN_REQUEST_MAX_ATTEMPTS:
                    raise
                time.sleep(TOKEN_REQUEST_BACKOFF_SECONDS * attempt)

        raise RuntimeError("Failed to mint GitHub App installation token after retries")

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
