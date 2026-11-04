from __future__ import annotations

import hmac
import json
from typing import Any
from typing import ClassVar
from typing import Iterator

import pytest
import responses
import sentry_sdk
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport

from src import main
from src.sentry_config import SENTRY_CONFIG_API_URL
from src.web_app_handler import WebAppHandler
from tests.helpers import sentry_config_response
from tests.helpers import WEBHOOK_SECRET

TOKEN = "ghs_installationtokenvalue"


class CapturingTransport(Transport):
    events: ClassVar[list[Any]] = []

    def capture_envelope(self, envelope: Envelope) -> None:
        self.events.extend(
            item.payload.json for item in envelope.items if item.type == "event"
        )


@pytest.fixture
def app_sentry() -> Iterator[list[Any]]:
    CapturingTransport.events = []
    main.init_sentry("https://key@o1.ingest.sentry.io/1", transport=CapturingTransport)
    yield CapturingTransport.events
    sentry_sdk.init()


@responses.activate
def test_github_tokens_are_scrubbed_from_app_errors(
    monkeypatch: pytest.MonkeyPatch,
    gh_app_env: None,
    app_sentry: list[Any],
    webhook_event: dict[str, Any],
) -> None:
    monkeypatch.setattr(main, "handler", WebAppHandler())

    data = webhook_event["payload"]
    data["installation"] = {"id": 1}
    org = data["repository"]["owner"]["login"]
    responses.post(
        "https://api.github.com/app/installations/1/access_tokens",
        json={"token": TOKEN},
    )
    responses.delete("https://api.github.com/installation/token", status=204)
    responses.get(
        SENTRY_CONFIG_API_URL.replace("{owner}", org),
        json=sentry_config_response("https://foo@o1.ingest.sentry.io/2"),
    )
    # Fails after the token is in the request headers and the token response
    responses.get(data["workflow_job"]["run_url"], status=502)

    body = json.dumps(data).encode()
    signature = hmac.new(
        WEBHOOK_SECRET.encode(), msg=body, digestmod="sha256"
    ).hexdigest()
    resp = main.app.test_client().post(
        "/",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "workflow_job",
            "X-Hub-Signature-256": f"sha256={signature}",
        },
    )
    sentry_sdk.flush()

    assert resp.status_code == 500
    assert app_sentry, "the error should reach Sentry"
    assert TOKEN not in json.dumps(app_sentry)
