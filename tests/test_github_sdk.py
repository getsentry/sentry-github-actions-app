from datetime import datetime
from unittest.mock import patch

import requests
import responses
from freezegun import freeze_time
from sentry_sdk.utils import format_timestamp

from src.github_sdk import GithubClient
from .fixtures import *

dsn_url = "https://foo@random.ingest.sentry.io/bar"


def test_job_without_steps(skipped_workflow):
    sdk = GithubClient(dsn_url)
    assert sdk.send_trace(skipped_workflow) == None


def test_initialize_without_setting_dsn():
    with pytest.raises(TypeError):
        GithubClient()


@freeze_time()
@responses.activate
@patch("src.github_sdk.get_uuid")
def test_trace_generation(
    mock_get_uuid,
    jobA_job,
    jobA_runs,
    jobA_workflow,
    jobA_trace,
    uuid_list,
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
    client = GithubClient(dsn=dsn_url)
    assert client._generate_trace(jobA_job) == jobA_trace


@freeze_time()
@responses.activate
@patch("src.github_sdk.get_uuid")
def test_send_trace(
    mock_get_uuid,
    jobA_job,
    jobA_runs,
    jobA_workflow,
    uuid_list,
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

    responses.post("https://foo@random.ingest.sentry.io/api/bar/envelope/")

    client = GithubClient(dsn_url)
    resp = client.send_trace(jobA_job)
    # This cannot happen in a fixture, otherwise, there will be a tiny bit of a clock drift
    now = datetime.utcnow()

    envelope_headers = {
        "User-Agent": f"python-requests/{requests.__version__}",
        "Accept-Encoding": "gzip, deflate",
        "Accept": "*/*",
        "Connection": "keep-alive",
        "event_id": "a401d83c7ec0495f82a8da8d9a389f5b",
        "sent_at": format_timestamp(now),
        "Content-Type": "application/x-sentry-envelope",
        "Content-Encoding": "gzip",
        "X-Sentry-Auth": f"Sentry sentry_key=foo,sentry_client=gha-sentry/0.0.1,sentry_timestamp={now},sentry_version=7",
        "Content-Length": "701",
    }

    for k, v in resp.request.headers.items():
        assert envelope_headers[k] == v

    # XXX: We will deal with this another time
    # assert (
    #     resp.request.body
    #     == b"\x1f\x8b\x08\x00\xf1\x16}b\x02\xff\xb5TM\x8f\xd30\x10\xbd\xef\xaf\x88|\x02\xa9m\x1c\xc7\x89\x93H\x08\xd0\x8a;\x12\x9c@\xa8\x9a\xd8\xe3&\xbb\xf9\"vX\xaa\xaa\xff\x1d{\xdb\xee\x97\x96n\xcb\x8aS\xd3\x99\xf1\xf8\xbd7o\xbc\xd9^l\x88]\x0fH\nbG\xe8\x0cH[\xf7\x1d\x99\x11\xd9w\x16;\xbb\xdc'a\x18\x9aZ\x82O\x86W\xe6\xb6\xa2\xc1ne+RD\x19\xa7\xbe\r\xfe\xf2\xf5\xb5r\xd5\t \x139H\x95g\x8c\xcbRC\x96P\xceh\x14K]\xea\xac\x14\xee\xf4\xb3\x97>\xfcW\x10=\xdebP\x81EcM\xf0\x86\xbe=\xe0\xfam\r)6\xbe\\\xa2\xff0\x03t\xbb\x9b\x81\xd3He\xb1\x14()\xcf\x13\xbdk*q\x97\xcd\xa2\x92\x96\x08)\xa0\xd2<\x8b\x04\x08\xaeb\xa6\x04Ms\x9a)\xcd\x1e\xe1r\xadgD\x81\x05\x7f\xc3U_\xbahe\xed`\x8a0\\\xd5\xb6\x9a\xca\x85\xec\xdbp\x85\xd68\xde\xe3:\xdc\xff\x8cSg\xc2$KD\xc2\x04O\xe8{Y\xa1\xbc^\x9a\xa9\xb6\xb8\xd4\xbd\x9c\xcc;;N\xbe\xf50\x9e\xd8q\x98\x9a&\x8c\xe3\x98\x0b\xb2\x9d\x91~\xf8\x9b4\n\x8d\x1c\xeb\xe1\x98z\xc6\x82\x9d\x9cv\xa4\xbf&[\xd7l28zz\x1d\xb4\x9e\xf5\xc7\xaaE\x15|\xb2\xa8\xd7\xae\x18[\xa8\x1b\xaf\xa9\x8f.\xd0G#\xf6a\xe5\xa3\x1e\xa8\x07\xe3\xfa\x8d\xce#u\xeb\xee\x80\xd6#c\x94\xb19\xe5s\x9a~\x8d\xf2\"aE$\xbeyY\x9f/a\xb4\xa0I\x11\xefJ`e\xf6R/\xefp\x9aIJ4\xc6\xa5K\xe7\rY\x1d\xe0\x84\xa0\xd4\xdc\xa1\xae\xbb\xd5\xbc\x81\xb5c\xe1\xad\xd1\xb6\xb5\xf5\xd4U.R\x16e\x90s\x95\x01\x95\x8aQ\xe7\x88(B\x10\xaa\xc44\x93\x89\x88Qs\xe5\xce\x8c8\xf4\xee\xc4S\xcd}f\xea\x96`-\xb6\x83k\x19\xcd\xc8M?^\xeb\xa6\xbf\xf1\x08\x1c\xa6\xc1:8\xb8X\xb7\x8d\x1f\xa5\x9b\xd0r\xc4\x9f\x93\xe3H\x8a\xdbQyq\x9c+\x1d\x87\xef\x9b\xdd\xcc\xbe\xa0\r\xa6!\xf0N\x9a\x1d\x04\x7f\x14\x1b`\xf4\x1bt\xd4\xcc\xf7I*X\xaaK\x0e,\xe6\x11\x17B\x92\xd3\xa6\x91.(\xa5G&\xb2+c\xf4\xae\xec\x8c\xed\xd9\xce\xf6T?;=\x82U%\xc7E\xdd?\xf0\xf3n\xb3\xe7\x95m\x9b\xb9\xed\xe7u\x0b+,\x1a\xf0\x06\xbd\x97\xe4\x9f\xce\x9e'\x1d\x08!RT\x11S\x00\x9c\xe7\xe5i\xd2=\xd0\xe4XY\x92\xbdN\xba\xde\xd8\xe0\xd2\xbf\x19\xfdd\x83;7\x1e\xc4y>{\x1e\xfd\x14\x9da\xb4\x8e\x05\xd39\xcf3x\x89\xfeaI_\xa0\xbf/K^E\xff\xb2o\x87\xc6=5\x8f\xd7\xe4I\xf4<\xba\x8e\xa2\xdbWT\x98\xe8\x88\xbb\xa7\xe1D\xba\xc9\xff\xa4\xfbc{\xf1\x07Hk>,{\x07\x00\x00"
    # )
