"""
This module contains the logic to support running the app as a Github App
"""
import base64
import os
import time

import jwt
import requests


class GithubAppClient:
    def __init__(self, private_key, app_id, installation_id) -> None:
        self.headers = get_authentication_header(private_key, app_id)
        self.installation_id = installation_id

    def get_token(self):
        token_info = get_token(self.installation_id, self.headers)
        return token_info["token"], token_info["expires_at"]


def get_jwt_token(private_key, app_id):
    payload = {
        # issued at time, 60 seconds in the past to allow for clock drift
        "iat": int(time.time()) - 60,
        # JWT expiration time (5 minutes maximum)
        "exp": int(time.time()) + 5 * 60,
        # GitHub App's identifier
        "iss": app_id,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


def get_authentication_header(private_key, app_id):
    jwt_token = get_jwt_token(private_key, app_id)
    return {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {jwt_token}",
    }


# From docs: Installation access tokens have the permissions
# configured by the GitHub App and expire after one hour.
# XXX: Create solution to get a new token
def get_token(installation_id, headers):
    req = requests.post(
        url=f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        headers=headers,
    )
    req.raise_for_status()
    resp = req.json()
    # This token expires in an hour
    return resp
