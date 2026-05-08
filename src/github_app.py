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

from .github_http import github_request

logger = logging.getLogger(__name__)


class GithubAppToken:
    def __init__(self, private_key, app_id) -> None:
        self.headers = self.get_authentication_header(private_key, app_id)

    # From docs: Installation access tokens have the permissions
    # configured by the GitHub App and expire after one hour.
    @contextlib.contextmanager
    def get_token(self, installation_id: int) -> Generator[str, None, None]:
        req = github_request(
            "post",
            url=f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers=self.headers,
            max_attempts=1,
        )
        req.raise_for_status()
        resp = req.json()
        try:
            # This token expires in an hour
            yield resp["token"]
        finally:
            try:
                github_request(
                    "delete",
                    "https://api.github.com/installation/token",
                    headers={"Authorization": f"token {resp['token']}"},
                )
            except requests.RequestException:
                logger.warning(
                    "Failed to revoke GitHub installation token; it will expire automatically.",
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
