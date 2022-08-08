import responses

from src.sentry_config import (
    SENTRY_CONFIG_API_URL as api_url,
    SENTRY_CONFIG_RAW_URL as raw_url,
    fetch_dsn_for_github_org,
)

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
    "download_url": "https://raw.githubusercontent.com/armenzg/.sentry/main/sentry_config.ini",
    "type": "file",
    "content": "OyBUaGlzIGZpbGUgbmVlZHMgdG8gYmUgcGxhY2VkIHdpdGhpbiBhIHByaXZh\ndGUgcmVwb3NpdG9yeSBuYW1lZCAuc2VudHJ5IChpdCBjYW4gYWxzbyBiZSBt\nYWRlIHB1YmxpYykKOyBUaGlzIGZpbGUgZm9yIG5vdyB3aWxsIGNvbmZpZ3Vy\nZSB0aGUgc2VudHJ5LWdpdGh1Yi1hY3Rpb25zLWFwcAo7IGJ1dCBpdCBtYXli\nZSB1c2VkIGJ5IGZ1dHVyZSBTZW50cnkgc2VydmljZXMKCjsgVGhpcyBjb25m\naWd1cmVzIGh0dHBzOi8vZ2l0aHViLmNvbS9nZXRzZW50cnkvc2VudHJ5LWdp\ndGh1Yi1hY3Rpb25zLWFwcAo7IEZvciBub3cgaXQgaXMgb25seSB1c2VkIHRv\nIGNvbmZpZ3VyZSB0aGUgcHJvamVjdCB5b3Ugd2FudCB5b3VyIG9yZydzIENJ\nCjsgdG8gcG9zdCB0cmFuc2FjdGlvbnMgdG8KW3NlbnRyeS1naXRodWItYWN0\naW9ucy1hcHBdCjsgVGhpcyBwcm9qZWN0IGlzIHVuZGVyIHNlbnRyeS1lY29z\neXN0ZW0gb3JnCjsgaHR0cHM6Ly9zZW50cnkuaW8vb3JnYW5pemF0aW9ucy9z\nZW50cnktZWNvc3lzdGVtL3BlcmZvcm1hbmNlLz9wcm9qZWN0PTY2Mjc1MDcK\nZHNuID0gaHR0cHM6Ly83MzgwNWVlMGE2Nzk0MzhkOTA5YmIwZTZlMDVmYjk3\nZkBvNTEwODIyLmluZ2VzdC5zZW50cnkuaW8vNjYyNzUwNw==\n",
    "encoding": "base64",
    "_links": {
        "self": "https://api.github.com/repos/armenzg/.sentry/contents/sentry_config.ini?ref=main",
        "git": "https://api.github.com/repos/armenzg/.sentry/git/blobs/21a49641b349f82af39b3ef5f54613a556e60fcc",
        "html": "https://github.com/armenzg/.sentry/blob/main/sentry_config.ini",
    },
}

sentry_config_ini_file = f"[sentry-github-actions-app]\ndsn = {expected_dsn}"


class TestSentryConfigCase:
    def setUp(self):
        self.api_url = api_url.replace("owner", "armenzg")
        self.raw_url = raw_url.replace("owner", "armenzg")

    @responses.activate
    def test_fetch_parse_sentry_config_file(self):
        responses.get(self.api_url, json=sentry_config_file_meta, status=200)
        responses.get(self.raw_url, body=sentry_config_ini_file, status=200)

        dsn = fetch_dsn_for_github_org("armenzg")
        assert dsn == expected_dsn

    def test_fetch_private_repo(self):
        pass

    def test_file_missing(self):
        pass

    def test_bad_contents(self):
        pass
