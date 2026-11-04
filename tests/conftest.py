from __future__ import annotations

import json
from typing import Any

import pytest

from src import sentry_config


def _load_fixture(path: str) -> dict[str, Any]:
    with open(path) as f:
        fixture: dict[str, Any] = json.load(f)
    return fixture


@pytest.fixture(autouse=True)
def clear_config_cache() -> None:
    sentry_config._config_cache.clear()


@pytest.fixture
def jobA_job() -> dict[str, Any]:
    return _load_fixture("tests/fixtures/jobA/job.json")


@pytest.fixture
def jobA_runs() -> dict[str, Any]:
    return _load_fixture("tests/fixtures/jobA/runs.json")


@pytest.fixture
def skipped_workflow() -> dict[str, Any]:
    return _load_fixture("tests/fixtures/skipped_workflow.json")


@pytest.fixture
def jobA_trace() -> dict[str, Any]:
    return _load_fixture("tests/fixtures/jobA/trace.json")


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
    return _load_fixture("tests/fixtures/webhook_event.json")


@pytest.fixture
def failure_job() -> dict[str, Any]:
    return _load_fixture("tests/fixtures/failedJob/job.json")


@pytest.fixture
def failure_runs() -> dict[str, Any]:
    return _load_fixture("tests/fixtures/failedJob/runs.json")
