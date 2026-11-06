from __future__ import annotations

import hmac
from typing import Any
from typing import ClassVar
from typing import Iterator

import pytest
import sentry_sdk
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport

from src import main
from tests.helpers import WEBHOOK_SECRET


class CapturingTransport(Transport):
    transactions: ClassVar[list[Any]] = []

    def capture_envelope(self, envelope: Envelope) -> None:
        self.transactions.extend(
            item.payload.json for item in envelope.items if item.type == "transaction"
        )


@pytest.fixture
def app_transactions(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[Any]]:
    monkeypatch.setenv("GH_WEBHOOK_SECRET", WEBHOOK_SECRET)
    CapturingTransport.transactions = []
    main.init_sentry("https://key@o1.ingest.sentry.io/1", transport=CapturingTransport)
    yield CapturingTransport.transactions
    sentry_sdk.init()


def _post(body: bytes, signature: str) -> int:
    client = main.create_app().test_client()
    resp = client.post(
        "/",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "ping",
            "X-Hub-Signature-256": f"sha256={signature}",
        },
    )
    sentry_sdk.flush()
    return resp.status_code


def _sign(body: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode(), msg=body, digestmod="sha256").hexdigest()


def test_unsigned_request_is_not_traced(app_transactions: list[Any]) -> None:
    assert _post(b"{}", "0" * 64) == 400
    assert app_transactions == []


def test_oversized_request_is_rejected_and_not_traced(
    app_transactions: list[Any],
) -> None:
    body = b" " * (main.MAX_PAYLOAD_BYTES + 1)
    assert _post(body, _sign(body)) == 413
    assert app_transactions == []


def test_signed_request_is_traced(app_transactions: list[Any]) -> None:
    body = b"{}"
    assert _post(body, _sign(body)) == 200
    assert len(app_transactions) == 1
