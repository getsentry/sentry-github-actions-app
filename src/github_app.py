import os
from datetime import datetime as dt

import jwt
import requests


def foo():
    # Open the file as f.
    # The function readlines() reads the file.
    with open("sentry-github-app-prototype.2022-05-25.private-key.pem", "rb") as f:
        private_key = f.readlines()

    payload = {
        # issued at time, 60 seconds in the past to allow for clock drift
        "iat": dt.utcnow() - dt.timedelta(minutes=1),
        # JWT expiration time (10 minute maximum)
        "exp": dt.utcnow() + dt.timedelta(minutes=10),
        # GitHub App's identifier
        "iss": os.environ["GH_APP_ID"],
    }

    token = jwt.encode(payload, private_key, algorithm="RS256")

    # $ curl -i -H "Authorization: Bearer YOUR_JWT" -H "Accept: application/vnd.github.v3+json" https://api.github.com/app
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {token}",
    }

    req = requests.get("https://api.github.com/app", headers=headers)
    import pdb

    pdb.set_trace()

    # XXX: Where could I find the public key?
    # jwt.decode(token, public_key, algorithms=["RS256"])


if __name__ == "__main__":
    foo()
