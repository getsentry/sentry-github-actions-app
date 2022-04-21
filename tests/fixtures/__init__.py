import json

import pytest


@pytest.fixture
def workflow():
    with open("tests/fixtures/workflow.json") as f:
        return json.load(f)


@pytest.fixture
def runs():
    with open("tests/fixtures/runs.json") as f:
        return json.load(f)


@pytest.fixture
def skipped_workflow():
    with open("tests/fixtures/skipped_workflow.json") as f:
        return json.load(f)


@pytest.fixture
def generated_transaction():
    with open("tests/fixtures/generated_transaction.json") as f:
        return json.load(f)
