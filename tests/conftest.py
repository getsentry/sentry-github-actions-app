import json

import pytest


@pytest.fixture
def jobA_job():
    with open("tests/fixtures/jobA/job.json") as f:
        return json.load(f)


@pytest.fixture
def jobA_runs():
    with open("tests/fixtures/jobA/runs.json") as f:
        return json.load(f)


@pytest.fixture
def jobA_workflow():
    with open("tests/fixtures/jobA/workflow.json") as f:
        return json.load(f)


@pytest.fixture
def skipped_workflow():
    with open("tests/fixtures/skipped_workflow.json") as f:
        return json.load(f)


@pytest.fixture
def jobA_trace():
    with open("tests/fixtures/jobA/trace.json") as f:
        return json.load(f)


@pytest.fixture
def uuid_list():
    return [
        "5ae279acd9824cbfa85042013cfbf8b7",
        "a401d83c7ec0495f82a8da8d9a389f5b",
        "81b0bea6aedf4817a74d32d706908df2",
        "0726fb4a2341477cbfa36ebd830bd8e3",
        "a7776ed12daa449bb0642e9ea1bb4152",
        "6e147ff372f9498abb5749a1210d8e0a",
        "498cceede5f14fd991778f007b237803",
        "a401d83c7ec0495f82a8da8d9a389f5b",
    ]


@pytest.fixture
def webhook_event():
    with open("tests/fixtures/webhook_event.json") as f:
        return json.load(f)
