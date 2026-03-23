"""
Tests for refactored WebAppHandler with hierarchical workflow tracing.

This module tests the integration between WebAppHandler and WorkflowJobCollector,
including feature flag behavior and backward compatibility.
"""

import os
import unittest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.web_app_handler import WebAppHandler


class TestWebAppHandlerRefactored(unittest.TestCase):
    """Test suite for refactored WebAppHandler."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock the config initialization
        with patch('src.web_app_handler.init_config'):
            self.handler = WebAppHandler(dry_run=True)
        
        # Create sample webhook data
        self.sample_job_data = {
            "action": "completed",
            "workflow_job": {
                "id": 123,
                "run_id": 456,
                "name": "test-job",
                "conclusion": "success",
                "started_at": datetime.utcnow().isoformat() + "Z",
                "completed_at": datetime.utcnow().isoformat() + "Z",
                "html_url": "https://github.com/test/repo/actions/runs/456/jobs/123",
                "steps": [],
                "head_branch": "main",
                "head_sha": "abc123",
                "run_attempt": 1,
                "workflow_name": "Test Workflow"
            },
            "repository": {
                "owner": {
                    "login": "test-org"
                }
            },
            "installation": {
                "id": 789
            }
        }
        
        self.sample_headers = {
            "X-GitHub-Event": "workflow_job"
        }

    def test_init(self):
        """Test WebAppHandler initialization."""
        with patch('src.web_app_handler.init_config'):
            handler = WebAppHandler(dry_run=True)
        
        self.assertTrue(handler.dry_run)
        self.assertEqual(len(handler.job_collectors), 0)

    def test_handle_event_unsupported_event(self):
        """Test handling of unsupported event types."""
        headers = {"X-GitHub-Event": "push"}
        
        reason, http_code = self.handler.handle_event(self.sample_job_data, headers)
        
        self.assertEqual(http_code, 200)
        self.assertEqual(reason, "Event not supported.")

    def test_handle_event_unsupported_action(self):
        """Test handling of unsupported actions."""
        data = self.sample_job_data.copy()
        data["action"] = "in_progress"
        
        reason, http_code = self.handler.handle_event(data, self.sample_headers)
        
        self.assertEqual(http_code, 200)
        self.assertEqual(reason, "We cannot do anything with this workflow state.")

    def test_handle_event_dry_run(self):
        """Test that dry run mode returns early."""
        reason, http_code = self.handler.handle_event(
            self.sample_job_data,
            self.sample_headers
        )
        
        # In dry run, should return OK without processing
        self.assertEqual(http_code, 200)
        self.assertEqual(reason, "OK")

    @patch.dict(os.environ, {"APP_DSN": "https://test@sentry.io/123"})
    def test_handle_event_hierarchical_tracing(self):
        """Test event handling with hierarchical tracing enabled."""
        with patch('src.web_app_handler.init_config'):
            handler = WebAppHandler(dry_run=False)
        
        # Mock the job collector
        mock_collector = Mock()
        mock_collector.is_hierarchical_tracing_enabled.return_value = True
        
        with patch.object(handler, '_get_job_collector', return_value=mock_collector):
            reason, http_code = handler.handle_event(
                self.sample_job_data,
                self.sample_headers
            )
        
        # Verify hierarchical tracing was used
        mock_collector.add_job.assert_called_once_with(self.sample_job_data)
        self.assertEqual(http_code, 200)
        self.assertEqual(reason, "OK")

    @patch.dict(os.environ, {"APP_DSN": "https://test@sentry.io/123"})
    def test_handle_event_legacy_tracing(self):
        """Test event handling with legacy tracing (hierarchical disabled)."""
        with patch('src.web_app_handler.init_config'):
            handler = WebAppHandler(dry_run=False)
        
        # Mock the job collector
        mock_collector = Mock()
        mock_collector.is_hierarchical_tracing_enabled.return_value = False
        
        with patch.object(handler, '_get_job_collector', return_value=mock_collector):
            with patch.object(handler, '_send_legacy_trace') as mock_legacy:
                reason, http_code = handler.handle_event(
                    self.sample_job_data,
                    self.sample_headers
                )
        
        # Verify legacy tracing was used
        mock_collector.add_job.assert_not_called()
        mock_legacy.assert_called_once()
        self.assertEqual(http_code, 200)

    @patch.dict(os.environ, {}, clear=True)
    def test_handle_event_no_dsn(self):
        """Test event handling when DSN is not configured."""
        with patch('src.web_app_handler.init_config'):
            handler = WebAppHandler(dry_run=False)
        
        reason, http_code = handler.handle_event(
            self.sample_job_data,
            self.sample_headers
        )
        
        self.assertEqual(http_code, 500)
        self.assertEqual(reason, "No DSN configured for webhook testing")

    def test_get_job_collector_creates_new(self):
        """Test that _get_job_collector creates a new collector if needed."""
        org = "test-org"
        token = "test-token"
        dsn = "https://test@sentry.io/123"
        
        with patch('src.web_app_handler.WorkflowJobCollector') as mock_collector_class:
            collector1 = self.handler._get_job_collector(org, token, dsn)
            
            # Verify collector was created
            mock_collector_class.assert_called_once_with(dsn, token, True)

    def test_get_job_collector_reuses_existing(self):
        """Test that _get_job_collector reuses existing collector."""
        org = "test-org"
        token = "test-token"
        dsn = "https://test@sentry.io/123"
        
        with patch('src.web_app_handler.WorkflowJobCollector') as mock_collector_class:
            collector1 = self.handler._get_job_collector(org, token, dsn)
            collector2 = self.handler._get_job_collector(org, token, dsn)
            
            # Verify collector was created only once
            mock_collector_class.assert_called_once()
            
            # Verify same instance is returned
            self.assertIs(collector1, collector2)

    def test_get_job_collector_separate_orgs(self):
        """Test that different orgs get separate collectors."""
        token = "test-token"
        dsn = "https://test@sentry.io/123"
        
        with patch('src.web_app_handler.WorkflowJobCollector') as mock_collector_class:
            collector1 = self.handler._get_job_collector("org1", token, dsn)
            collector2 = self.handler._get_job_collector("org2", token, dsn)
            
            # Verify two collectors were created
            self.assertEqual(mock_collector_class.call_count, 2)

    @patch.dict(os.environ, {"APP_DSN": "https://test@sentry.io/123"})
    def test_send_legacy_trace(self):
        """Test legacy trace sending."""
        with patch('src.web_app_handler.init_config'):
            handler = WebAppHandler(dry_run=False)
        
        with patch('src.web_app_handler.GithubClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            
            handler._send_legacy_trace(
                self.sample_job_data,
                "test-org",
                "test-token",
                "https://test@sentry.io/123"
            )
            
            # Verify GithubClient was created and send_trace called
            mock_client_class.assert_called_once_with(
                "test-token",
                "https://test@sentry.io/123",
                False
            )
            mock_client.send_trace.assert_called_once_with(self.sample_job_data)

    def test_handle_event_missing_installation(self):
        """Test handling event with missing installation field."""
        data = self.sample_job_data.copy()
        del data["installation"]
        
        with patch.dict(os.environ, {"APP_DSN": "https://test@sentry.io/123"}):
            with patch('src.web_app_handler.init_config'):
                handler = WebAppHandler(dry_run=False)
            
            mock_collector = Mock()
            mock_collector.is_hierarchical_tracing_enabled.return_value = True
            
            with patch.object(handler, '_get_job_collector', return_value=mock_collector):
                reason, http_code = handler.handle_event(data, self.sample_headers)
            
            # Should still process with default installation_id
            self.assertEqual(http_code, 200)
            mock_collector.add_job.assert_called_once()

    def test_valid_signature_no_secret(self):
        """Test signature validation when no secret is configured."""
        self.handler.config = Mock()
        self.handler.config.gh = Mock()
        self.handler.config.gh.webhook_secret = None
        
        result = self.handler.valid_signature(b"test body", {})
        self.assertTrue(result)

    def test_valid_signature_with_secret(self):
        """Test signature validation with webhook secret."""
        import hmac
        
        secret = "test-secret"
        body = b"test body"
        
        # Generate valid signature
        signature = hmac.new(
            secret.encode(),
            msg=body,
            digestmod="sha256"
        ).hexdigest()
        
        self.handler.config = Mock()
        self.handler.config.gh = Mock()
        self.handler.config.gh.webhook_secret = secret
        
        headers = {"X-Hub-Signature-256": f"sha256={signature}"}
        
        result = self.handler.valid_signature(body, headers)
        self.assertTrue(result)

    def test_valid_signature_invalid(self):
        """Test signature validation with invalid signature."""
        self.handler.config = Mock()
        self.handler.config.gh = Mock()
        self.handler.config.gh.webhook_secret = "test-secret"
        
        headers = {"X-Hub-Signature-256": "sha256=invalid"}
        
        result = self.handler.valid_signature(b"test body", headers)
        self.assertFalse(result)


class TestWebAppHandlerIntegration(unittest.TestCase):
    """Integration tests for WebAppHandler with real WorkflowJobCollector."""

    @patch.dict(os.environ, {"APP_DSN": "https://test@sentry.io/123"})
    @patch('src.workflow_job_collector.ENABLE_HIERARCHICAL_TRACING', True)
    def test_full_workflow_with_hierarchical_tracing(self):
        """Test full workflow processing with hierarchical tracing enabled."""
        with patch('src.web_app_handler.init_config'):
            handler = WebAppHandler(dry_run=False)
        
        # Create multiple jobs for same workflow
        run_id = 12345
        jobs = [
            {
                "action": "completed",
                "workflow_job": {
                    "id": i,
                    "run_id": run_id,
                    "name": f"job-{i}",
                    "conclusion": "success",
                    "started_at": datetime.utcnow().isoformat() + "Z",
                    "completed_at": datetime.utcnow().isoformat() + "Z",
                    "html_url": f"https://github.com/test/repo/runs/{run_id}/jobs/{i}",
                    "steps": [],
                    "head_branch": "main",
                    "head_sha": "abc123",
                    "run_attempt": 1,
                    "workflow_name": "Test"
                },
                "repository": {
                    "owner": {"login": "test-org"}
                },
                "installation": {"id": 789}
            }
            for i in range(3)
        ]
        
        headers = {"X-GitHub-Event": "workflow_job"}
        
        # Mock the WorkflowTracer to avoid actual API calls
        with patch('src.workflow_job_collector.WorkflowTracer'):
            # Process all jobs
            for job_data in jobs:
                reason, http_code = handler.handle_event(job_data, headers)
                self.assertEqual(http_code, 200)
        
        # Verify collector was created for org
        self.assertIn("test-org", handler.job_collectors)
        
        # Verify all jobs were collected
        collector = handler.job_collectors["test-org"]
        self.assertEqual(len(collector.workflow_jobs[run_id]), 3)


if __name__ == '__main__':
    unittest.main()

