from __future__ import annotations

from unittest.mock import Mock
from unittest.mock import patch

import requests

from src.github_app import GITHUB_API_TIMEOUT_SECONDS
from src.github_app import GithubAppToken


def test_get_token_suppresses_installation_token_revoke_timeout(caplog):
    app_token = GithubAppToken.__new__(GithubAppToken)
    app_token.headers = {"Authorization": "Bearer jwt"}

    post_response = Mock()
    post_response.json.return_value = {"token": "installation-token"}

    with patch("src.github_app.requests.post", return_value=post_response) as mock_post:
        with patch(
            "src.github_app.requests.delete",
            side_effect=requests.ConnectTimeout(),
        ) as mock_delete:
            with app_token.get_token(installation_id=123) as token:
                assert token == "installation-token"

    post_response.raise_for_status.assert_called_once()
    mock_post.assert_called_once_with(
        url="https://api.github.com/app/installations/123/access_tokens",
        headers={"Authorization": "Bearer jwt"},
        timeout=GITHUB_API_TIMEOUT_SECONDS,
    )
    mock_delete.assert_called_once_with(
        "https://api.github.com/installation/token",
        headers={"Authorization": "token installation-token"},
        timeout=GITHUB_API_TIMEOUT_SECONDS,
    )
    assert "Failed to revoke GitHub installation token" in caplog.text
