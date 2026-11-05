from __future__ import annotations

import responses

import cli
from src import REQUEST_TIMEOUT


def test_parse_job_url() -> None:
    assert cli._parse_job_url(
        "https://github.com/getsentry/sentry/runs/5759197422?check_suite_focus=true"
    ) == ("getsentry", "sentry", "5759197422")


@responses.activate
def test_fetch_job_is_authenticated_with_a_timeout() -> None:
    responses.get(
        "https://api.github.com/repos/getsentry/sentry/actions/jobs/1",
        json={"id": 1},
    )

    assert cli._fetch_job("getsentry", "sentry", "1", "installation_token") == {"id": 1}
    (call,) = responses.calls
    assert call.request.headers["Authorization"] == "token installation_token"
    assert call.request.req_kwargs["timeout"] == REQUEST_TIMEOUT
