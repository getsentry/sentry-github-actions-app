import os
from datetime import datetime as dt, timedelta

import jwt
import requests


def get_private_key(file_path=None, gcp_secret=None):
    assert file_path or gcp_secret
    private_key = None
    if file_path:
        # Open the file as f.
        # The function readlines() reads the file.
        with open(file_path, "rb") as f:
            private_key = f.read()
    else:
        raise NotImplemented()
    return private_key


def get_jwt_token(private_key):
    payload = {
        # issued at time, 60 seconds in the past to allow for clock drift
        "iat": dt.utcnow() - timedelta(minutes=1),
        # JWT expiration time (10 minute maximum)
        "exp": dt.utcnow() + timedelta(minutes=10),
        # GitHub App's identifier
        "iss": os.environ["GH_APP_ID"],
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
