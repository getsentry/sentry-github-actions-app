"""
This module contains the logic to support running the app as a Github App
"""
from __future__ import annotations

import contextlib
import logging
import time
from typing import Generator

import jwt
import requests


class GithubAppToken:
    TOKEN_REQUEST_TIMEOUT_SECONDS = 10
    TOKEN_REQUEST_MAX_ATTEMPTS = 3
    TOKEN_REQUEST_RETRY_BACKOFF_SECONDS = 1

    def __init__(self, private_key, app_id) -> None:
        self.headers = self.get_authentication_header(private_key, app_id)

    def _fetch_installation_access_token(self, installation_id: int):
        for attempt in range(1, self.TOKEN_REQUEST_MAX_ATTEMPTS + 1):
            try:
                req = requests.post(
                    url=f"https://api.github.com/app/installations/{installation_id}/access_tokens",
                    headers=self.headers,
                    timeout=self.TOKEN_REQUEST_TIMEOUT_SECONDS,
                )
                req.raise_for_status()
                return req.json()
            except requests.exceptions.ConnectTimeout:
                if attempt >= self.TOKEN_REQUEST_MAX_ATTEMPTS:
                    raise
                logging.warning(
                    "Connect timeout requesting GitHub App token for installation %s; retrying (%s/%s)",
                    installation_id,
                    attempt,
                    self.TOKEN_REQUEST_MAX_ATTEMPTS,
                )
                # Linear backoff avoids hot-looping when GitHub API is flaky.
                time.sleep(self.TOKEN_REQUEST_RETRY_BACKOFF_SECONDS * attempt)

    # From docs: Installation access tokens have the permissions
    # configured by the GitHub App and expire after one hour.
    @contextlib.contextmanager
    def get_token(self, installation_id: int) -> Generator[str, None, None]:
        resp = self._fetch_installation_access_token(installation_id)
        try:
            # This token expires in an hour
            yield resp["token"]
        finally:
            try:
                requests.delete(
                    "https://api.github.com/installation/token",
                    headers={"Authorization": f"token {resp['token']}"},
                    timeout=self.TOKEN_REQUEST_TIMEOUT_SECONDS,
                )
            except requests.exceptions.RequestException:
                logging.warning(
                    "Failed to revoke temporary GitHub App token for installation %s",
                    installation_id,
                    exc_info=True,
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
