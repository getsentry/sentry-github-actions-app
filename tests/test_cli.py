from __future__ import annotations

import responses

import cli
from src import REQUEST_TIMEOUT


def test_parse_job_url():
    assert cli._parse_job_url(
        "https://github.com/getsentry/sentry/runs/5759197422?check_suite_focus=true"
    ) == ("getsentry", "sentry", "5759197422")


@responses.activate
def test_fetch_job_is_authenticated_with_a_timeout(monkeypatch):
    responses.get(
        "https://api.github.com/repos/getsentry/sentry/actions/jobs/1",
        json={"id": 1},
    )
    timeouts = []
    original_get = cli.requests.get

    def get(*args, **kwargs):
        timeouts.append(kwargs.get("timeout"))
        return original_get(*args, **kwargs)

    monkeypatch.setattr(cli.requests, "get", get)

    assert cli._fetch_job("getsentry", "sentry", "1", "installation_token") == {"id": 1}
    assert responses.calls[0].request.headers["Authorization"] == (
        "token installation_token"
    )
    assert timeouts == [REQUEST_TIMEOUT]
