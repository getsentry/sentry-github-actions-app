import json

import pytest


@pytest.fixture
def completed_workflow():
    with open("tests/fixtures/wf_completed.json") as f:
        return json.load(f)


@pytest.fixture
def generated_transaction():
    with open("tests/fixtures/generated_transaction.json") as f:
        return json.load(f)
