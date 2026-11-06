from __future__ import annotations

from src import main


def test_oversized_body_is_rejected() -> None:
    client = main.create_app().test_client()
    resp = client.post(
        "/",
        data=b"x" * (main.MAX_WEBHOOK_BYTES + 1),
        headers={"Content-Type": "application/json", "X-GitHub-Event": "workflow_job"},
    )

    assert resp.status_code == 413
