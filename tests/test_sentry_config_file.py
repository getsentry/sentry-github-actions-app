from __future__ import annotations

import base64
from unittest import TestCase

import pytest
import responses
from requests import HTTPError

from src.sentry_config import fetch_dsn_for_github_org
from src.sentry_config import SENTRY_CONFIG_API_URL as api_url

expected_dsn = (
    "https://73805ee0a679438d909bb0e6e05fb97f@o510822.ingest.sentry.io/6627507"
)
sentry_config_file_meta = {
    "name": "sentry_config.ini",
    "path": "sentry_config.ini",
    "sha": "21a49641b349f82af39b3ef5f54613a556e60fcc",
    "size": 619,
    "url": "https://api.github.com/repos/armenzg/.sentry/contents/sentry_config.ini?ref=main",
    "html_url": "https://github.com/armenzg/.sentry/blob/main/sentry_config.ini",
    "git_url": "https://api.github.com/repos/armenzg/.sentry/git/blobs/21a49641b349f82af39b3ef5f54613a556e60fcc",
    "download_url": "https://raw.githubusercontent.com/armenzg/.sentry/main/sentry_config.ini?token=A2NWFUXUKJYCKJQXPAUSHULC6KTXLAVPNFXHG5DBNRWGC5DJN5XF62LEZYA2YZLLWFUW443UMFWGYYLUNFXW4X3UPFYGLN2JNZ2GKZ3SMF2GS33OJFXHG5DBNRWGC5DJN5XA",
    "type": "file",
    "content": "OyBUaGlzIGZpbGUgbmVlZHMgdG8gYmUgcGxhY2VkIHdpdGhpbiBhIHByaXZh\ndGUgcmVwb3NpdG9yeSBuYW1lZCAuc2VudHJ5IChpdCBjYW4gYWxzbyBiZSBt\nYWRlIHB1YmxpYykKOyBUaGlzIGZpbGUgZm9yIG5vdyB3aWxsIGNvbmZpZ3Vy\nZSB0aGUgc2VudHJ5LWdpdGh1Yi1hY3Rpb25zLWFwcAo7IGJ1dCBpdCBtYXli\nZSB1c2VkIGJ5IGZ1dHVyZSBTZW50cnkgc2VydmljZXMKCjsgVGhpcyBjb25m\naWd1cmVzIGh0dHBzOi8vZ2l0aHViLmNvbS9nZXRzZW50cnkvc2VudHJ5LWdp\ndGh1Yi1hY3Rpb25zLWFwcAo7IEZvciBub3cgaXQgaXMgb25seSB1c2VkIHRv\nIGNvbmZpZ3VyZSB0aGUgcHJvamVjdCB5b3Ugd2FudCB5b3VyIG9yZydzIENJ\nCjsgdG8gcG9zdCB0cmFuc2FjdGlvbnMgdG8KW3NlbnRyeS1naXRodWItYWN0\naW9ucy1hcHBdCjsgVGhpcyBwcm9qZWN0IGlzIHVuZGVyIHNlbnRyeS1lY29z\neXN0ZW0gb3JnCjsgaHR0cHM6Ly9zZW50cnkuaW8vb3JnYW5pemF0aW9ucy9z\nZW50cnktZWNvc3lzdGVtL3BlcmZvcm1hbmNlLz9wcm9qZWN0PTY2Mjc1MDcK\nZHNuID0gaHR0cHM6Ly83MzgwNWVlMGE2Nzk0MzhkOTA5YmIwZTZlMDVmYjk3\nZkBvNTEwODIyLmluZ2VzdC5zZW50cnkuaW8vNjYyNzUwNw==\n",
    "encoding": "base64",
    "_links": {
        "self": "https://api.github.com/repos/armenzg/.sentry/contents/sentry_config.ini?ref=main",
        "git": "https://api.github.com/repos/armenzg/.sentry/git/blobs/21a49641b349f82af39b3ef5f54613a556e60fcc",
        "html": "https://github.com/armenzg/.sentry/blob/main/sentry_config.ini",
    },
}
org = "armenzg"
token = "foo_token"
installation_id = 1


def config_file_meta(dsn: str) -> dict:
    contents = f"[sentry-github-actions-app]\ndsn = {dsn}\n"
    return {
        **sentry_config_file_meta,
        "content": base64.b64encode(contents.encode()).decode(),
    }


class TestSentryConfigCase(TestCase):
    def setUp(self) -> None:
        self.api_url = api_url.replace("{owner}", org)
        responses.add(
            method="GET",
            url=self.api_url,
            json=sentry_config_file_meta,
            status=200,
        )
        return super().setUp()

    @responses.activate
    def test_fetch_parse_sentry_config_file(self) -> None:
        assert fetch_dsn_for_github_org(org, token, installation_id) == expected_dsn

    @responses.activate
    def test_dsn_is_cached_per_installation_and_org(self) -> None:
        other_org_dsn = "https://e0bb9a6e1c4f4d3c9b3a6c2d8f1e7a5b@o1.ingest.sentry.io/2"
        other_org_api_url = api_url.replace("{owner}", "other-org")
        responses.get(other_org_api_url, json=config_file_meta(other_org_dsn))

        # Every webhook comes with a new token
        assert fetch_dsn_for_github_org(org, "token_1", 1) == expected_dsn
        assert fetch_dsn_for_github_org(org, "token_2", 1) == expected_dsn
        assert fetch_dsn_for_github_org("other-org", "token_3", 2) == other_org_dsn
        responses.assert_call_count(self.api_url, 1)
        responses.assert_call_count(other_org_api_url, 1)

        # Another installation has to be able to read the org's config itself
        responses.replace(responses.GET, self.api_url, status=404)
        with pytest.raises(HTTPError):
            fetch_dsn_for_github_org(org, "token_4", 2)

    @responses.activate
    def test_failed_fetch_is_not_cached(self) -> None:
        responses.replace(responses.GET, self.api_url, status=403)
        with pytest.raises(HTTPError):
            fetch_dsn_for_github_org(org, token, installation_id)

        # e.g. the org's GitHub API rate limit has been reset
        responses.replace(
            responses.GET,
            self.api_url,
            json=sentry_config_file_meta,
            status=200,
        )
        assert fetch_dsn_for_github_org(org, token, installation_id) == expected_dsn

    @responses.activate
    def test_failed_fetch_does_not_expose_cached_dsns(self) -> None:
        fetch_dsn_for_github_org(org, token, installation_id)
        responses.get(api_url.replace("{owner}", "other-org"), status=403)

        with pytest.raises(HTTPError) as excinfo:
            fetch_dsn_for_github_org("other-org", token, 2)

        # Sentry sends every frame's local variables along with an error
        tb = excinfo.tb
        while tb:
            assert expected_dsn not in repr(tb.tb_frame.f_locals)
            tb = tb.tb_next

    @responses.activate
    def test_fetch_for_longest_github_login(self) -> None:
        # GitHub logins are up to 39 characters
        login = "a" * 38 + "z"
        responses.get(api_url.replace("{owner}", login), json=sentry_config_file_meta)
        assert fetch_dsn_for_github_org(login, token, installation_id) == expected_dsn

    @responses.activate
    def test_invalid_github_login(self) -> None:
        for login in ["a" * 40, "-armenzg", "armenzg/../evil", ""]:
            with self.subTest(login=login), self.assertRaises(ValueError):
                fetch_dsn_for_github_org(login, token, installation_id)
        assert len(responses.calls) == 0

    def test_fetch_private_repo(self) -> None:
        pass

    def test_file_missing(self) -> None:
        pass

    def test_bad_contents(self) -> None:
        pass
