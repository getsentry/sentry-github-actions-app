from unittest.mock import patch

import responses
from freezegun import freeze_time

from src.trace import _base_transaction, send_trace, _generate_trace
from .fixtures import *


@patch("src.trace.get_uuid")
def test_base_transaction(mock_get_uuid, jobA_job, uuid_list):
    mock_get_uuid.side_effect = uuid_list

    assert _base_transaction(jobA_job) == {
        "event_id": uuid_list[0],
        "contexts": {
            "trace": {
                "span_id": uuid_list[1][:16],
                "trace_id": uuid_list[2],
                "type": "trace",
            }
        },
        "transaction": "default",
        "type": "transaction",
        "user": {},
        "start_timestamp": "2022-04-06T19:52:17Z",
        "timestamp": "2022-04-06T20:05:37Z",
        "transaction": "frontend tests (0)",
    }


@responses.activate
def test_job_without_steps(skipped_workflow):
    assert send_trace(skipped_workflow) == None


@freeze_time()
@responses.activate
@patch("src.trace.get_uuid")
def test_job_basic_test(
    mock_get_uuid, jobA_job, jobA_runs, jobA_workflow, jobA_trace, uuid_list
):
    mock_get_uuid.side_effect = uuid_list
    responses.get(
        "https://api.github.com/repos/getsentry/sentry/actions/runs/2104746951",
        json=jobA_runs,
    )
    responses.get(
        "https://api.github.com/repos/getsentry/sentry/actions/workflows/1174556",
        json=jobA_workflow,
    )
    assert _generate_trace(jobA_job) == jobA_trace
