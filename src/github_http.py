from __future__ import annotations

import logging
from typing import Any

import requests

GITHUB_API_TIMEOUT = 10
GITHUB_API_MAX_ATTEMPTS = 2

logger = logging.getLogger(__name__)


def github_request(
    method: str,
    url: str,
    *,
    max_attempts: int = GITHUB_API_MAX_ATTEMPTS,
    **kwargs: Any,
) -> requests.Response:
    kwargs.setdefault("timeout", GITHUB_API_TIMEOUT)

    for attempt in range(1, max_attempts + 1):
        try:
            return requests.request(method, url, **kwargs)
        except (requests.ConnectionError, requests.Timeout):
            if attempt == max_attempts:
                raise
            logger.warning(
                "Retrying GitHub API request after a transient network error.",
                exc_info=True,
            )

    raise RuntimeError("Unreachable GitHub request retry state.")
