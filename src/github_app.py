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

logger = logging.getLogger(__name__)

GITHUB_API_TIMEOUT_SECONDS = 5
GITHUB_API_MAX_ATTEMPTS = 3
GITHUB_API_RETRYABLE_ERRORS = (
    requests.ConnectionError,
    requests.Timeout,
    requests.exceptions.SSLError,
)


class GithubAppToken:
    def __init__(self, private_key, app_id) -> None:
        self.headers = self.get_authentication_header(private_key, app_id)

    # From docs: Installation access tokens have the permissions
    # configured by the GitHub App and expire after one hour.
    @contextlib.contextmanager
    def get_token(self, installation_id: int) -> Generator[str, None, None]:
        req = _request_github_with_retries(
            requests.post,
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers=self.headers,
        )
        req.raise_for_status()
        resp = req.json()
        try:
            # This token expires in an hour
            yield resp["token"]
        finally:
            try:
                _request_github_with_retries(
                    requests.delete,
                    "https://api.github.com/installation/token",
                    headers={"Authorization": f"token {resp['token']}"},
                )
            except GITHUB_API_RETRYABLE_ERRORS as e:
                logger.warning("Failed to revoke GitHub installation token: %s", e)

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


def _request_github_with_retries(method, url, **kwargs):
    kwargs.setdefault("timeout", GITHUB_API_TIMEOUT_SECONDS)
    for attempt in range(GITHUB_API_MAX_ATTEMPTS):
        try:
            return method(url, **kwargs)
        except GITHUB_API_RETRYABLE_ERRORS:
            if attempt == GITHUB_API_MAX_ATTEMPTS - 1:
                raise
            time.sleep(2**attempt)
