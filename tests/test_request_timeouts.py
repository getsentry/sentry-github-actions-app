from __future__ import annotations

import base64
from urllib.parse import urlparse

import responses

from src import REQUEST_TIMEOUT
from src.github_app import GithubAppToken
from src.sentry_config import SENTRY_CONFIG_API_URL
from src.web_app_handler import WebAppHandler


@responses.activate
def test_every_request_has_a_timeout(monkeypatch, webhook_event, jobA_runs):
    # Github App mode, so that the installation token is minted and revoked too
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.setenv("GH_APP_ID", "1")
    monkeypatch.setenv("GH_APP_PRIVATE_KEY", base64.b64encode(b"irrelevant").decode())
    monkeypatch.setattr(
        GithubAppToken, "get_jwt_token", lambda self, private_key, app_id: "jwt"
    )

    data = webhook_event["payload"]
    data["installation"] = {"id": 1}
    org = data["repository"]["owner"]["login"]
    dsn = "https://foo@o1.ingest.sentry.io/2"
    config = f"[sentry-github-actions-app]\ndsn = {dsn}\n"

    responses.post(
        "https://api.github.com/app/installations/1/access_tokens",
        json={"token": "installation_token"},
    )
    responses.delete("https://api.github.com/installation/token", status=204)
    responses.get(
        SENTRY_CONFIG_API_URL.replace("{owner}", org),
        json={
            "type": "file",
            "encoding": "base64",
            "content": base64.b64encode(config.encode()).decode(),
        },
    )
    responses.get(data["workflow_job"]["run_url"], json=jobA_runs)
    responses.get(
        jobA_runs["workflow_url"], json={"path": ".github/workflows/acceptance.yml"}
    )
    responses.post("https://foo@o1.ingest.sentry.io/api/2/envelope/")

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
