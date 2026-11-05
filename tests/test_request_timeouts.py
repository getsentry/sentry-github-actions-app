from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import responses

from src import REQUEST_TIMEOUT
from src.sentry_config import SENTRY_CONFIG_API_URL
from src.web_app_handler import WebAppHandler
from tests.helpers import sentry_config_response


@responses.activate
def test_every_request_has_a_timeout(
    # Github App mode, so that the installation token is minted and revoked too
    gh_app_env: None,
    webhook_event: dict[str, Any],
    jobA_runs: dict[str, Any],
) -> None:
    data = webhook_event["payload"]
    data["installation"] = {"id": 1}
    org = data["repository"]["owner"]["login"]

    responses.post(
        "https://api.github.com/app/installations/1/access_tokens",
        json={"token": "installation_token"},
    )
    responses.delete("https://api.github.com/installation/token", status=204)
    responses.get(
        SENTRY_CONFIG_API_URL.replace("{owner}", org),
        json=sentry_config_response("https://foo@o1.ingest.sentry.io/2"),
    )
    responses.get(data["workflow_job"]["run_url"], json=jobA_runs)
    responses.post("https://o1.ingest.sentry.io/api/2/envelope/")

    handler = WebAppHandler()
    assert handler.config.gh_app
    assert handler.handle_event(data, webhook_event["headers"]) == ("OK", 200)

    called_paths = {urlparse(call.request.url).path for call in responses.calls}
    assert called_paths >= {
        "/app/installations/1/access_tokens",
        f"/repos/{org}/.sentry/contents/sentry_config.ini",
        urlparse(data["workflow_job"]["run_url"]).path,
        "/api/2/envelope/",
        "/installation/token",
    }
    for call in responses.calls:
        assert call.request.req_kwargs["timeout"] == REQUEST_TIMEOUT, call.request.url
