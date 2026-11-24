from __future__ import annotations

from typing import TYPE_CHECKING

from sentry_sdk.utils import iter_event_stacktraces

if TYPE_CHECKING:
    from sentry_sdk._types import Event
    from sentry_sdk._types import Hint

FILTERED = "[Filtered]"
# The denylist of the SDK 2.x EventScrubber, which 3.0 removed
SENSITIVE_KEYS = frozenset(
    {
        "_csrf",
        "_csrf_token",
        "_session",
        "_xsrf",
        "aiohttp_session",
        "api_key",
        "apikey",
        "auth",
        "authorization",
        "connect.sid",
        "cookie",
        "credentials",
        "csrf",
        "csrf_token",
        "csrftoken",
        "ip_address",
        "mysql_pwd",
        "passwd",
        "password",
        "phpsessid",
        "private_key",
        "privatekey",
        "proxy-authorization",
        "remote_addr",
        "secret",
        "session",
        "sessionid",
        "set_cookie",
        "symfony",
        "token",
        "user_session",
        "x_api_key",
        "x_csrftoken",
        "x_forwarded_for",
        "x_real_ip",
        "xsrf-token",
    }
)


def _scrub(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in SENSITIVE_KEYS:
                value[key] = FILTERED
            else:
                _scrub(item)
    elif isinstance(value, list):
        for item in value:
            _scrub(item)


def scrub_event(event: Event, hint: Hint) -> Event:
    """Filter sensitive keys at any depth, as `EventScrubber(recursive=True)` did."""
    request = event.get("request")
    if isinstance(request, dict):
        for field in ("headers", "cookies", "data"):
            _scrub(request.get(field))
    _scrub(event.get("extra"))
    _scrub(event.get("user"))
    breadcrumbs = event.get("breadcrumbs")
    if isinstance(breadcrumbs, dict):
        for crumb in breadcrumbs.get("values", []):
            _scrub(crumb.get("data"))
    for stacktrace in iter_event_stacktraces(event):
        if isinstance(stacktrace, dict):
            for frame in stacktrace.get("frames") or ():
                _scrub(frame.get("vars"))
    return event
