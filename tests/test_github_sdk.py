from unittest.mock import patch

import responses
from freezegun import freeze_time

from src.github_sdk import GithubSentryError, send_envelope, send_trace, _generate_trace
from .fixtures import *


@responses.activate
def test_job_without_steps(skipped_workflow):
    assert send_trace(skipped_workflow) == None


def test_send_trace_without_setting_dsn(jobA_trace):
    with pytest.raises(GithubSentryError):
        assert send_envelope(jobA_trace)


@freeze_time()
@responses.activate
@patch("src.github_sdk.get_uuid")
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
