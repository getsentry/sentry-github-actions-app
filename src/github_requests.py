from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_RETRIES = 2
DEFAULT_RETRY_DELAY_SECONDS = 0.5
RETRYABLE_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
)


def github_request(
    method: str,
    url: str,
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    retries: int = DEFAULT_RETRIES,
    retry_delay: float = DEFAULT_RETRY_DELAY_SECONDS,
    **kwargs: Any,
) -> requests.Response:
    """Make a GitHub API request resilient to transient network failures."""
    attempts = retries + 1
    for attempt in range(1, attempts + 1):
        try:
            return requests.request(method, url, timeout=timeout, **kwargs)
        except RETRYABLE_EXCEPTIONS:
            if attempt == attempts:
                raise
            logger.warning(
                "GitHub API %s request failed; retrying (%s/%s).",
                method.upper(),
                attempt,
                attempts,
                exc_info=True,
            )
            time.sleep(retry_delay * attempt)

    raise RuntimeError("unreachable")
