from __future__ import annotations

# (connect, read) seconds for every outgoing request. Without a timeout, a hung
# connection blocks one of gunicorn's few threads indefinitely.
REQUEST_TIMEOUT = (5, 10)
