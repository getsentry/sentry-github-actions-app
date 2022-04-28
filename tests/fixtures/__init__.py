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
