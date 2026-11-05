from __future__ import annotations

import gzip
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import responses
from freezegun import freeze_time
from requests import HTTPError
from sentry_sdk.envelope import Envelope
from sentry_sdk.utils import BadDsn

from src.github_sdk import GithubClient
from src.github_sdk import GithubSentryError

DSN = "https://foo@random.ingest.sentry.io/1234"
TOKEN = "irrelevant"


@responses.activate
def test_skipped_job_is_not_sent(skipped_workflow: dict[str, Any]) -> None:
    sdk = GithubClient(dsn=DSN, token=TOKEN)
    assert sdk.send_trace(skipped_workflow) is None
    assert len(responses.calls) == 0


@pytest.mark.parametrize(
    "dsn, sentry_project_url",
    [
        (DSN, "https://random.ingest.sentry.io/api/1234/envelope/"),
        (
            "https://foo@o1.ingest.us.sentry.io/1234",
            "https://o1.ingest.us.sentry.io/api/1234/envelope/",
        ),
        (
            "http://foo:secret@sentry.example.com:9000/sentry/1234",
            "http://sentry.example.com:9000/sentry/api/1234/envelope/",
        ),
    ],
)
def test_initialize_with_dsn(dsn: str, sentry_project_url: str) -> None:
    client = GithubClient(dsn=dsn, token=TOKEN)
    assert client.sentry_key == "foo"
    assert client.sentry_project_url == sentry_project_url


@pytest.mark.parametrize(
    "dsn",
    [
        # Seen in an org's sentry_config.ini
        "dsn: <>",
        "",
        "https://random.ingest.sentry.io/1234",
        "https://foo@random.ingest.sentry.io/",
        "https://foo@random.ingest.sentry.io/1234/",
    ],
)
def test_initialize_with_invalid_dsn(dsn: str) -> None:
    with pytest.raises(BadDsn):
        GithubClient(dsn=dsn, token=TOKEN)


@responses.activate
def test_ensure_raise_error_on_github_api_failure() -> None:
    """We want to delegate to the app using the SDK to handle the error."""
    url = "https://api.github.com/repos/getsentry/sentry/actions/runs/2104746951"
    responses.get(url, status=500)
    client = GithubClient(dsn=DSN, token=TOKEN)
    with pytest.raises(HTTPError) as excinfo:
        client._fetch_github(url)
    assert excinfo.value.response is not None
    assert excinfo.value.response.status_code == 500


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/repos/getsentry/sentry/actions/runs/2104746951",
        "http://api.github.com/repos/getsentry/sentry/actions/runs/2104746951",
        "https://api.github.com.example.com/repos/getsentry/sentry/actions/runs/2104746951",
        "https://api.github.com@example.com/repos/getsentry/sentry/actions/runs/2104746951",
        "https://github.com/getsentry/sentry/actions/runs/2104746951",
    ],
)
@responses.activate
def test_fetch_github_only_sends_the_token_to_the_github_api(url: str) -> None:
    with pytest.raises(GithubSentryError):
        GithubClient(dsn=DSN, token=TOKEN)._fetch_github(url)
    assert len(responses.calls) == 0


@freeze_time()
@responses.activate
@patch("src.github_sdk.get_uuid")
def test_trace_generation(
    mock_get_uuid: MagicMock,
    jobA_job: dict[str, Any],
    jobA_runs: dict[str, Any],
    jobA_trace: dict[str, Any],
    uuid_list: list[str],
) -> None:
    mock_get_uuid.side_effect = uuid_list
    responses.get(
        "https://api.github.com/repos/getsentry/sentry/actions/runs/2104746951",
        json=jobA_runs,
    )
    client = GithubClient(dsn=DSN, token=TOKEN)
    trace = client._generate_trace(jobA_job)
    assert trace == jobA_trace

    # make sure there is no failing step for passing runs
    assert "failing_step" not in trace["tags"]


@responses.activate
def test_trace_generation_with_failing_steps(
    failure_job: dict[str, Any], failure_runs: dict[str, Any]
) -> None:
    responses.get(
        failure_job["run_url"],
        json=failure_runs,
    )

    client = GithubClient(dsn=DSN, token=TOKEN)
    trace = client._generate_trace(failure_job)

    # make sure the failing step exists
    assert trace["tags"]["failing_step"] == "Run calculate tests"
    assert trace["tags"]["event"] == "push"


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/acceptance.yml",
        ".github/workflows/acceptance.yml@main",
        "getsentry/.github/.github/workflows/acceptance.yml@refs/heads/main",
        "getsentry/.github/.github/workflows/acceptance.yml@1595d4b6de6a9e9751fb270a41019ce507d4099e",
    ],
)
@responses.activate
def test_trace_generation_for_required_workflow(
    jobA_job: dict[str, Any], jobA_runs: dict[str, Any], path: str
) -> None:
    # Fetching a required workflow's `workflow_url` fails with a 422, and `responses`
    # raises on any request that isn't registered
    jobA_runs[
        "workflow_url"
    ] = "https://api.github.com/repos/getsentry/sentry/actions/required_workflows/1"
    # A required workflow's path can name the repo it lives in and end in a ref
    jobA_runs["path"] = path
    responses.get(jobA_job["run_url"], json=jobA_runs)

    trace = GithubClient(dsn=DSN, token=TOKEN)._generate_trace(jobA_job)

    assert trace["tags"]["workflow"] == "acceptance.yml"
    assert len(responses.calls) == 1


@freeze_time("2022-04-12 10:00:00")
@responses.activate
@patch("src.github_sdk.get_uuid")
def test_send_trace(
    mock_get_uuid: MagicMock,
    jobA_job: dict[str, Any],
    jobA_runs: dict[str, Any],
    jobA_trace: dict[str, Any],
    uuid_list: list[str],
) -> None:
    mock_get_uuid.side_effect = uuid_list
    responses.get(
        "https://api.github.com/repos/getsentry/sentry/actions/runs/2104746951",
        json=jobA_runs,
    )
    responses.post("https://random.ingest.sentry.io/api/1234/envelope/")

    resp = GithubClient(dsn=DSN, token=TOKEN).send_trace(jobA_job)

    assert resp is not None
    request = resp.request
    assert request.headers["Content-Type"] == "application/x-sentry-envelope"
    assert request.headers["Content-Encoding"] == "gzip"
    assert request.headers["X-Sentry-Auth"] == (
        "Sentry sentry_key=foo,sentry_client=gha-sentry/0.0.1,"
        "sentry_timestamp=2022-04-12 10:00:00,sentry_version=7"
    )
    assert isinstance(request.body, bytes)
    envelope = Envelope.deserialize(gzip.decompress(request.body))
    (item,) = envelope.items
    assert item.type == "transaction"
    assert item.payload.json == jobA_trace
