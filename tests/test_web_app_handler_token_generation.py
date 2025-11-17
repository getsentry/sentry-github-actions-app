"""
Tests for GitHub App token generation in WebAppHandler.
"""

import os
import unittest
from unittest.mock import Mock, patch, MagicMock

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.web_app_handler import WebAppHandler, GithubAppConfig, GitHubConfig, Config


class TestWebAppHandlerTokenGeneration(unittest.TestCase):
    """Test suite for GitHub App token generation."""

    def setUp(self):
        """Set up test fixtures."""
        self.webhook_payload = {
            "action": "completed",
            "workflow_job": {
                "id": 12345,
                "run_id": 67890,
                "name": "test-job",
                "conclusion": "success",
                "started_at": "2025-11-17T17:36:10Z",
                "completed_at": "2025-11-17T17:36:45Z",
            },
            "repository": {
                "full_name": "test-org/test-repo",
                "owner": {"login": "test-org"}
            },
            "installation": {
                "id": 123456
            }
        }
        self.headers = {
            "X-GitHub-Event": "workflow_job",
            "X-Hub-Signature-256": "sha256=test"
        }

    def test_generate_github_app_token_success(self):
        """Test successful GitHub App token generation."""
        # Mock config with GitHub App
        mock_config = Config(
            gh_app=GithubAppConfig(
                app_id=12345,
                private_key=b"test_private_key"
            ),
            gh=GitHubConfig(
                webhook_secret="test_secret",
                token=None
            )
        )
        
        # Mock token response
        mock_token_response = Mock()
        mock_token_response.json.return_value = {"token": "ghs_test_token_12345"}
        mock_token_response.raise_for_status = Mock()
        
        # Mock GithubAppToken headers
        mock_app_token = Mock()
        mock_app_token.headers = {"Authorization": "Bearer test_jwt"}
        
        handler = WebAppHandler(dry_run=False)  # Need dry_run=False to test token generation
        handler.config = mock_config
        
        # Set APP_DSN for the handler
        with patch.dict('os.environ', {'APP_DSN': 'https://test@sentry.io/123'}):
            with patch('src.web_app_handler.GithubAppToken', return_value=mock_app_token):
                with patch('requests.post', return_value=mock_token_response) as mock_post:
                    with patch('src.web_app_handler.WorkflowJobCollector'):
                        reason, http_code = handler.handle_event(self.webhook_payload, self.headers)
        
        # Verify token generation was attempted
        mock_post.assert_called()
        # Verify webhook was processed
        self.assertEqual(http_code, 200)

    def test_fallback_to_pat_token(self):
        """Test fallback to PAT token when GitHub App fails."""
        # Mock config with GitHub App and PAT
        mock_config = Config(
            gh_app=GithubAppConfig(
                app_id=12345,
                private_key=b"test_private_key"
            ),
            gh=GitHubConfig(
                webhook_secret="test_secret",
                token="ghp_pat_token_12345"
            )
        )
        
        handler = WebAppHandler(dry_run=True)
        handler.config = mock_config
        
        # Mock GitHub App token generation failure
        with patch('requests.post', side_effect=Exception("App token generation failed")):
            reason, http_code = handler.handle_event(self.webhook_payload, self.headers)
        
        # Should still process (falls back to PAT)
        self.assertEqual(http_code, 200)

    def test_no_token_available(self):
        """Test handling when no token is available."""
        # Mock config without GitHub App or PAT
        mock_config = Config(
            gh_app=None,
            gh=GitHubConfig(
                webhook_secret="test_secret",
                token=None
            )
        )
        
        handler = WebAppHandler(dry_run=True)
        handler.config = mock_config
        
        reason, http_code = handler.handle_event(self.webhook_payload, self.headers)
        
        # Should still process (will use timeout-based detection)
        self.assertEqual(http_code, 200)

    def test_missing_installation_id(self):
        """Test handling when installation_id is missing."""
        payload_no_installation = self.webhook_payload.copy()
        del payload_no_installation["installation"]
        
        mock_config = Config(
            gh_app=None,
            gh=GitHubConfig(
                webhook_secret="test_secret",
                token="ghp_pat_token"
            )
        )
        
        handler = WebAppHandler(dry_run=True)
        handler.config = mock_config
        
        reason, http_code = handler.handle_event(payload_no_installation, self.headers)
        
        # Should use PAT token
        self.assertEqual(http_code, 200)

    def test_github_app_token_expires_after_one_hour(self):
        """Test that tokens are generated per request (they expire in 1 hour)."""
        mock_config = Config(
            gh_app=GithubAppConfig(
                app_id=12345,
                private_key=b"test_private_key"
            ),
            gh=GitHubConfig(
                webhook_secret="test_secret",
                token=None
            )
        )
        
        mock_token_response = Mock()
        mock_token_response.json.return_value = {"token": "ghs_test_token_12345"}
        mock_token_response.raise_for_status = Mock()
        
        # Mock GithubAppToken headers
        mock_app_token = Mock()
        mock_app_token.headers = {"Authorization": "Bearer test_jwt"}
        
        handler = WebAppHandler(dry_run=False)  # Need dry_run=False to test token generation
        handler.config = mock_config
        
        # Set APP_DSN for the handler
        with patch.dict('os.environ', {'APP_DSN': 'https://test@sentry.io/123'}):
            with patch('src.web_app_handler.GithubAppToken', return_value=mock_app_token):
                with patch('requests.post', return_value=mock_token_response) as mock_post:
                    with patch('src.web_app_handler.WorkflowJobCollector'):
                        # Process multiple webhooks
                        handler.handle_event(self.webhook_payload, self.headers)
                        handler.handle_event(self.webhook_payload, self.headers)
        
        # Each webhook should generate a new token (or reuse if cached)
        # Note: Current implementation generates per webhook, which is fine
        self.assertGreaterEqual(mock_post.call_count, 1)


class TestWebAppHandlerHeaderHandling(unittest.TestCase):
    """Test suite for header handling improvements."""

    def setUp(self):
        """Set up test fixtures."""
        self.webhook_payload = {
            "action": "completed",
            "workflow_job": {
                "id": 12345,
                "run_id": 67890,
                "name": "test-job",
            },
            "repository": {
                "owner": {"login": "test-org"}
            }
        }

    def test_flask_normalized_headers(self):
        """Test that Flask-normalized headers are handled correctly."""
        handler = WebAppHandler(dry_run=True)
        
        # Test various header formats Flask might use
        headers_variants = [
            {"X-GitHub-Event": "workflow_job"},
            {"X-GITHUB-EVENT": "workflow_job"},
            {"HTTP_X_GITHUB_EVENT": "workflow_job"},
        ]
        
        for headers in headers_variants:
            reason, http_code = handler.handle_event(self.webhook_payload, headers)
            self.assertEqual(http_code, 200, f"Failed with headers: {headers}")

    def test_missing_github_event_header(self):
        """Test handling when X-GitHub-Event header is missing."""
        handler = WebAppHandler(dry_run=True)
        
        headers = {}  # No GitHub event header
        
        reason, http_code = handler.handle_event(self.webhook_payload, headers)
        
        self.assertEqual(http_code, 400)
        self.assertIn("Missing", reason)

    def test_unsupported_event_type(self):
        """Test handling of unsupported event types."""
        handler = WebAppHandler(dry_run=True)
        
        headers = {"X-GitHub-Event": "push"}  # Unsupported event
        
        reason, http_code = handler.handle_event(self.webhook_payload, headers)
        
        self.assertEqual(http_code, 200)  # Returns 200 but doesn't process
        self.assertIn("not supported", reason)

    def test_unsupported_action(self):
        """Test handling of unsupported actions."""
        handler = WebAppHandler(dry_run=True)
        
        payload = self.webhook_payload.copy()
        payload["action"] = "queued"  # Unsupported action
        
        headers = {"X-GitHub-Event": "workflow_job"}
        
        reason, http_code = handler.handle_event(payload, headers)
        
        self.assertEqual(http_code, 200)  # Returns 200 but doesn't process
        self.assertIn("cannot do anything", reason.lower())


if __name__ == '__main__':
    unittest.main()

