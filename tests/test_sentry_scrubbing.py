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
from tests.helpers import sentry_config_response
from tests.helpers import WEBHOOK_SECRET

TOKEN = "ghs_installationtokenvalue"
# The org's DSN key, from its .sentry repo
ORG_DSN_KEY = "0123456789abcdef0123456789abcdef"
# Payload data that no request URL or exception message carries
REPO_DESCRIPTION = "payload-only repository description"


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
def test_github_tokens_and_org_data_stay_out_of_app_errors(
    gh_app_env: None,
    app_sentry: list[Any],
    webhook_event: dict[str, Any],
) -> None:
    data = webhook_event["payload"]
    data["installation"] = {"id": 1}
    data["repository"]["description"] = REPO_DESCRIPTION
    org = data["repository"]["owner"]["login"]
    responses.post(
        "https://api.github.com/app/installations/1/access_tokens",
        json={"token": TOKEN},
    )
    responses.delete("https://api.github.com/installation/token", status=204)
    responses.get(
        SENTRY_CONFIG_API_URL.replace("{owner}", org),
        json=sentry_config_response(f"https://{ORG_DSN_KEY}@o1.ingest.sentry.io/2"),
    )
    # Fails after the token is in the request headers and the token response
    responses.get(data["workflow_job"]["run_url"], status=502)

    body = json.dumps(data).encode()
    signature = hmac.new(
        WEBHOOK_SECRET.encode(), msg=body, digestmod="sha256"
    ).hexdigest()
    client = main.create_app().test_client()
    resp = client.post(
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
    events = json.dumps(app_sentry)
    assert TOKEN not in events
    # Installations belong to other orgs, so their DSNs and (often private) CI data
    # stay out of the app's own events
    assert ORG_DSN_KEY not in events
    assert REPO_DESCRIPTION not in events
