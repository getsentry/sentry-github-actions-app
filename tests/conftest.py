from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src import sentry_config
from tests.helpers import WEBHOOK_SECRET

FIXTURES_DIR = Path(__file__).parent / "fixtures"
# The app picks its mode and credentials from these
APP_ENV_VARS = (
    "COMMIT_TRACES_ENABLED",
    "GH_APP_ID",
    "GH_APP_PRIVATE_KEY",
    "GH_TOKEN",
    "GH_WEBHOOK_SECRET",
    "K_SERVICE",
)


def _load_fixture(path: str) -> dict[str, Any]:
    with open(FIXTURES_DIR / path) as f:
        fixture: dict[str, Any] = json.load(f)
    return fixture


@pytest.fixture(autouse=True)
def clear_config_cache() -> None:
    sentry_config._config_cache.clear()


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # .envrc loads a developer's .env, which would otherwise change the app's mode
    for var in APP_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(scope="session")
def gh_app_private_key() -> str:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return base64.b64encode(pem).decode()


@pytest.fixture
def gh_app_env(monkeypatch: pytest.MonkeyPatch, gh_app_private_key: str) -> None:
    monkeypatch.setenv("GH_APP_ID", "1")
    monkeypatch.setenv("GH_APP_PRIVATE_KEY", gh_app_private_key)
    monkeypatch.setenv("GH_WEBHOOK_SECRET", WEBHOOK_SECRET)


@pytest.fixture
def jobA_job() -> dict[str, Any]:
    return _load_fixture("jobA/job.json")


@pytest.fixture
def jobA_runs() -> dict[str, Any]:
    return _load_fixture("jobA/runs.json")


@pytest.fixture
def skipped_workflow() -> dict[str, Any]:
    return _load_fixture("skipped_workflow.json")


@pytest.fixture
def jobA_trace() -> dict[str, Any]:
    return _load_fixture("jobA/trace.json")


@pytest.fixture
def uuid_list() -> list[str]:
    return [
        "5ae279acd9824cbfa85042013cfbf8b7",
        "a401d83c7ec0495f82a8da8d9a389f5b",
        "4d4d3477c624836b1b3a3729a7de688a",
        "0726fb4a2341477cbfa36ebd830bd8e3",
        "a7776ed12daa449bb0642e9ea1bb4152",
        "6e147ff372f9498abb5749a1210d8e0a",
        "a401d83c7ec0495f82a8da8d9a389f5b",
        "a401d83c7ec0495f82a8da8d9a389f5b",
    ]


@pytest.fixture
def webhook_event() -> dict[str, Any]:
    return _load_fixture("webhook_event.json")


@pytest.fixture
def failure_job() -> dict[str, Any]:
    return _load_fixture("failedJob/job.json")


@pytest.fixture
def failure_runs() -> dict[str, Any]:
    return _load_fixture("failedJob/runs.json")


@pytest.fixture
def commit_webhook_payload() -> dict[str, Any]:
    return _load_fixture("commit/webhook_payload.json")


@pytest.fixture
def commit_runs() -> dict[str, Any]:
    return _load_fixture("commit/runs.json")
