from unittest.mock import patch, MagicMock

import responses
from freezegun import freeze_time

from src.trace import _base_transaction, send_trace, _generate_trace
from .fixtures import *


HEX = "06a005dd99324b5e8b7f874be7d41568"


class UUID:
    def __init__(self, value):
        self.hex = value


@patch("src.trace.uuid.uuid4")
def test_base_transaction(mock_uuid):
    # XXX: Calling this should give us different values each time
    mock_uuid.return_value = UUID(HEX)

    assert _base_transaction() == {
        "contexts": {
            "trace": {
                "span_id": HEX[16:],
                "trace_id": HEX,
                "type": "trace",
            }
        },
        "event_id": HEX,
        "transaction": "default",
        "type": "transaction",
        "user": {},
    }


@responses.activate
def test_workflow_without_steps(skipped_workflow):
    assert send_trace(skipped_workflow) == None


@freeze_time()
@responses.activate
@patch("src.trace.uuid.uuid4")
def test_workflow_basic_test(mock_uuid, jobA_job, jobA_runs, jobA_workflow, jobA_trace):
    # XXX: Calling this should give us different values each time
    mock_uuid.return_value = UUID(HEX)
    responses.get(
        "https://api.github.com/repos/getsentry/sentry/actions/runs/2104746951",
        json=jobA_runs,
    )
    responses.get(
        "https://api.github.com/repos/getsentry/sentry/actions/workflows/1174556",
        json=jobA_workflow,
    )
    assert _generate_trace(jobA_job) == jobA_trace
