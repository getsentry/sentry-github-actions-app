from __future__ import annotations

import base64

WEBHOOK_SECRET = "fake_secret"


def sentry_config_response(dsn: str, extra: str = "") -> dict[str, str]:
    """GitHub's contents API response for an org's .sentry/sentry_config.ini."""
    contents = f"[sentry-github-actions-app]\ndsn = {dsn}\n{extra}"
    return {
        "type": "file",
        "encoding": "base64",
        "content": base64.b64encode(contents.encode()).decode(),
    }
