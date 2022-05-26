import os
from datetime import datetime as dt, timedelta

import jwt
import requests


def get_private_key():
    private_key = None
    if os.environ.get("GH_PRIVATE_KEY_PATH"):
        # Open the file as f.
        # The function readlines() reads the file.
        with open(os.environ["GH_PRIVATE_KEY_PATH"], "rb") as f:
            private_key = f.read()
    else:
        # XXX: On the next pass we need to support using Google Secrets
        raise NotImplemented()

    return private_key


def get_jwt_token(private_key, app_id):
    payload = {
        # issued at time, 60 seconds in the past to allow for clock drift
        "iat": dt.utcnow() - timedelta(minutes=1),
        # JWT expiration time (10 minute maximum)
        "exp": dt.utcnow() + timedelta(minutes=10),
        # GitHub App's identifier
        "iss": app_id,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


def get_org_for_token(token):
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {token}",
    }
    req = requests.get("https://api.github.com/app", headers=headers)
    req.raise_for_status()
    response = req.json()

    # The second value tracks the org this token is useful for
    return response["owner"]["login"]


def get_access_tokens():
    access_tokens = {}

    jwt_token = get_jwt_token(get_private_key(), os.environ["GH_APP_ID"])
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {jwt_token}",
    }

    req = requests.get(url="https://api.github.com/app/installations", headers=headers)
    req.raise_for_status()
    installations = req.json()

    # From docs: Installation access tokens have the permissions
    # configured by the GitHub App and expire after one hour.
    for inst in installations:
        req = requests.post(url=inst["access_tokens_url"], headers=headers)
        req.raise_for_status()
        access_tokens[inst["account"]["login"]] = req.json()

    return access_tokens
