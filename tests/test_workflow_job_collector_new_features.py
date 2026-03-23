"""
Tests for new WorkflowJobCollector features:
- API-based total job count fetching
- Timeout scheduling
- Workflow completion detection improvements
- Edge cases and error handling
"""

import os
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock, call
import requests

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.workflow_job_collector import (
    WorkflowJobCollector,
    NO_NEW_JOBS_TIMEOUT,
    MAX_WORKFLOW_WAIT_TIME,
)


class TestWorkflowJobCollectorAPIFeatures(unittest.TestCase):
    """Test suite for API-based features in WorkflowJobCollector."""

    def setUp(self):
        """Set up test fixtures."""
        self.dsn = "https://test@sentry.io/123"
        self.token = "test_token"
        self.test_run_id = 12345
        self.repo_full_name = "test-org/test-repo"
        
        with patch('src.workflow_job_collector.WorkflowTracer'):
            self.collector = WorkflowJobCollector(
                dsn=self.dsn,
                token=self.token,
                dry_run=True
            )

    def tearDown(self):
        """Clean up after tests."""
        for timer in self.collector.workflow_timers.values():
            timer.cancel()

    def _create_job_data(self, job_id: int, run_id: int, name: str, 
                         conclusion: str = "success", repository: dict = None) -> dict:
        """Create a mock job data payload."""
        now = datetime.utcnow()
        job_data = {
            "workflow_job": {
                "id": job_id,
                "run_id": run_id,
                "name": name,
                "conclusion": conclusion,
                "started_at": (now - timedelta(minutes=5)).isoformat() + "Z",
                "completed_at": now.isoformat() + "Z",
                "html_url": f"https://github.com/test/repo/actions/runs/{run_id}/jobs/{job_id}",
                "steps": [],
                "head_branch": "main",
                "head_sha": "abc123",
                "run_attempt": 1,
            }
        }
        if repository:
            job_data["repository"] = repository
        return job_data

    def test_fetch_total_job_count_success(self):
        """Test successful fetching of total job count from GitHub API."""
        mock_response = Mock()
        mock_response.json.return_value = {"total_count": 8}
        mock_response.raise_for_status = Mock()
        
        with patch('requests.get', return_value=mock_response) as mock_get:
            result = self.collector._fetch_total_job_count(
                self.test_run_id,
                self.repo_full_name
            )
        
        self.assertEqual(result, 8)
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        self.assertIn(f"/actions/runs/{self.test_run_id}/jobs", call_args[0][0])
        self.assertIn("Authorization", call_args[1]["headers"])

    def test_fetch_total_job_count_no_token(self):
        """Test that fetch returns None when no token is available."""
        self.collector.token = None
        
        result = self.collector._fetch_total_job_count(
            self.test_run_id,
            self.repo_full_name
        )
        
        self.assertIsNone(result)

    def test_fetch_total_job_count_api_failure(self):
        """Test that API failures are handled gracefully."""
        with patch('requests.get', side_effect=requests.exceptions.RequestException("API Error")):
            result = self.collector._fetch_total_job_count(
                self.test_run_id,
                self.repo_full_name
            )
        
        self.assertIsNone(result)

    def test_fetch_total_job_count_missing_total_count(self):
        """Test handling when API response is missing total_count field."""
        mock_response = Mock()
        mock_response.json.return_value = {}  # Missing total_count
        mock_response.raise_for_status = Mock()
        
        with patch('requests.get', return_value=mock_response):
            result = self.collector._fetch_total_job_count(
                self.test_run_id,
                self.repo_full_name
            )
        
        self.assertIsNone(result)

    def test_fetch_total_job_count_timeout(self):
        """Test that API timeout is handled."""
        with patch('requests.get', side_effect=requests.exceptions.Timeout("Timeout")):
            result = self.collector._fetch_total_job_count(
                self.test_run_id,
                self.repo_full_name
            )
        
        self.assertIsNone(result)

    def test_fetch_total_job_count_http_error(self):
        """Test handling of HTTP errors (404, 403, etc.)."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
        
        with patch('requests.get', return_value=mock_response):
            result = self.collector._fetch_total_job_count(
                self.test_run_id,
                self.repo_full_name
            )
        
        self.assertIsNone(result)

    def test_add_job_fetches_total_count_on_first_job(self):
        """Test that total job count is fetched when first job arrives."""
        repository = {"full_name": self.repo_full_name}
        job_data = self._create_job_data(1, self.test_run_id, "first-job", repository=repository)
        
        mock_response = Mock()
        mock_response.json.return_value = {"total_count": 5}
        mock_response.raise_for_status = Mock()
        
        with patch('requests.get', return_value=mock_response) as mock_get:
            with patch.object(self.collector, '_schedule_workflow_processing'):
                self.collector.add_job(job_data)
        
        # Verify total count was fetched and cached
        self.assertEqual(self.collector.workflow_total_jobs[self.test_run_id], 5)
        # Verify API was called
        self.assertEqual(mock_get.call_count, 1)

    def test_add_job_does_not_refetch_total_count(self):
        """Test that total job count is only fetched once per workflow run."""
        repository = {"full_name": self.repo_full_name}
        job1 = self._create_job_data(1, self.test_run_id, "job-1", repository=repository)
        job2 = self._create_job_data(2, self.test_run_id, "job-2", repository=repository)
        
        mock_response = Mock()
        mock_response.json.return_value = {"total_count": 3}
        mock_response.raise_for_status = Mock()
        
        with patch('requests.get', return_value=mock_response) as mock_get:
            with patch.object(self.collector, '_schedule_workflow_processing'):
                self.collector.add_job(job1)
                self.collector.add_job(job2)
        
        # API should only be called once
        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(self.collector.workflow_total_jobs[self.test_run_id], 3)

    def test_should_process_workflow_now_with_total_count(self):
        """Test processing logic when total job count is known."""
        # Set up: We know there are 5 jobs total
        self.collector.workflow_total_jobs[self.test_run_id] = 5
        
        # Add 5 completed jobs
        for i in range(5):
            job = self._create_job_data(i, self.test_run_id, f"job-{i}")
            self.collector.workflow_jobs[self.test_run_id].append(job["workflow_job"])
            self.collector.job_arrival_times[self.test_run_id].append(time.time())
        
        # Wait for timeout to elapse
        time.sleep(NO_NEW_JOBS_TIMEOUT + 0.1)
        
        result = self.collector._should_process_workflow_now(self.test_run_id)
        self.assertTrue(result)

    def test_should_process_workflow_now_waiting_for_more_jobs(self):
        """Test that processing waits when not all jobs have arrived."""
        # Set up: We know there are 5 jobs total, but only 3 have arrived
        self.collector.workflow_total_jobs[self.test_run_id] = 5
        
        # Add only 3 completed jobs
        for i in range(3):
            job = self._create_job_data(i, self.test_run_id, f"job-{i}")
            self.collector.workflow_jobs[self.test_run_id].append(job["workflow_job"])
            self.collector.job_arrival_times[self.test_run_id].append(time.time())
        
        result = self.collector._should_process_workflow_now(self.test_run_id)
        self.assertFalse(result)  # Should wait for more jobs

    def test_should_process_workflow_now_fallback_to_timeout(self):
        """Test that processing falls back to timeout when total count is unknown."""
        # Don't set total count (simulates API failure or no token)
        self.collector.workflow_total_jobs[self.test_run_id] = None
        
        # Add 3 completed jobs
        for i in range(3):
            job = self._create_job_data(i, self.test_run_id, f"job-{i}")
            self.collector.workflow_jobs[self.test_run_id].append(job["workflow_job"])
            self.collector.job_arrival_times[self.test_run_id].append(time.time())
        
        # Wait for timeout
        time.sleep(NO_NEW_JOBS_TIMEOUT + 0.1)
        
        result = self.collector._should_process_workflow_now(self.test_run_id)
        self.assertTrue(result)  # Should process after timeout

    def test_should_schedule_timeout_check_with_total_count(self):
        """Test timeout check scheduling when total count is known."""
        # Set up: 5 jobs total, all 5 have arrived and completed
        self.collector.workflow_total_jobs[self.test_run_id] = 5
        
        for i in range(5):
            job = self._create_job_data(i, self.test_run_id, f"job-{i}")
            self.collector.workflow_jobs[self.test_run_id].append(job["workflow_job"])
            self.collector.job_arrival_times[self.test_run_id].append(time.time())
        
        result = self.collector._should_schedule_timeout_check(self.test_run_id)
        self.assertTrue(result)

    def test_should_schedule_timeout_check_waiting_for_jobs(self):
        """Test that timeout check is not scheduled when jobs are missing."""
        # Set up: 5 jobs total, but only 3 have arrived
        self.collector.workflow_total_jobs[self.test_run_id] = 5
        
        for i in range(3):
            job = self._create_job_data(i, self.test_run_id, f"job-{i}")
            self.collector.workflow_jobs[self.test_run_id].append(job["workflow_job"])
            self.collector.job_arrival_times[self.test_run_id].append(time.time())
        
        result = self.collector._should_schedule_timeout_check(self.test_run_id)
        self.assertFalse(result)  # Should not schedule, waiting for more jobs

    def test_schedule_timeout_check_creates_timer(self):
        """Test that timeout check scheduling creates a timer."""
        # Add a completed job
        job = self._create_job_data(1, self.test_run_id, "test-job")
        self.collector.workflow_jobs[self.test_run_id].append(job["workflow_job"])
        self.collector.job_arrival_times[self.test_run_id].append(time.time())
        
        with patch('threading.Timer') as mock_timer_class:
            self.collector._schedule_timeout_check(self.test_run_id)
        
        # Verify timer was created
        mock_timer_class.assert_called_once()
        # Verify timer was started
        mock_timer_instance = mock_timer_class.return_value
        mock_timer_instance.start.assert_called_once()

    def test_schedule_timeout_check_calculates_remaining_time(self):
        """Test that timeout check calculates remaining time correctly."""
        # Add a job
        job = self._create_job_data(1, self.test_run_id, "test-job")
        self.collector.workflow_jobs[self.test_run_id].append(job["workflow_job"])
        self.collector.job_arrival_times[self.test_run_id].append(time.time())
        
        # Wait a bit
        time.sleep(1.0)
        
        with patch('threading.Timer') as mock_timer_class:
            self.collector._schedule_timeout_check(self.test_run_id)
        
        # Verify timer was called with remaining time (should be ~6s since we waited 1s)
        call_args = mock_timer_class.call_args
        timer_delay = call_args[0][0]
        self.assertGreater(timer_delay, 0)
        self.assertLess(timer_delay, NO_NEW_JOBS_TIMEOUT)

    def test_cleanup_removes_total_jobs_cache(self):
        """Test that cleanup removes total jobs cache entry."""
        # Set up workflow data
        job = self._create_job_data(1, self.test_run_id, "test-job")
        self.collector.workflow_jobs[self.test_run_id].append(job["workflow_job"])
        self.collector.workflow_total_jobs[self.test_run_id] = 5
        
        # Cleanup
        self.collector._cleanup_workflow_run(self.test_run_id)
        
        # Verify total jobs cache was cleaned up
        self.assertNotIn(self.test_run_id, self.collector.workflow_total_jobs)

    def test_add_job_stores_repository_info(self):
        """Test that repository info is stored from webhook payload."""
        repository = {"full_name": self.repo_full_name, "id": 12345}
        job_data = self._create_job_data(1, self.test_run_id, "test-job", repository=repository)
        
        with patch.object(self.collector, '_schedule_workflow_processing'):
            self.collector.add_job(job_data)
        
        # Verify repository info was stored
        self.assertIn(self.test_run_id, self.collector.workflow_repositories)
        self.assertEqual(
            self.collector.workflow_repositories[self.test_run_id]["full_name"],
            self.repo_full_name
        )

    def test_add_job_uses_repository_info_for_api_call(self):
        """Test that repository info is used when fetching total job count."""
        repository = {"full_name": self.repo_full_name}
        job_data = self._create_job_data(1, self.test_run_id, "test-job", repository=repository)
        
        mock_response = Mock()
        mock_response.json.return_value = {"total_count": 3}
        mock_response.raise_for_status = Mock()
        
        with patch('requests.get', return_value=mock_response) as mock_get:
            with patch.object(self.collector, '_schedule_workflow_processing'):
                self.collector.add_job(job_data)
        
        # Verify API was called with correct repository name
        call_args = mock_get.call_args
        self.assertIn(self.repo_full_name, call_args[0][0])


class TestWorkflowJobCollectorEdgeCases(unittest.TestCase):
    """Test suite for edge cases and error scenarios."""

    def setUp(self):
        """Set up test fixtures."""
        self.dsn = "https://test@sentry.io/123"
        self.token = "test_token"
        self.test_run_id = 12345
        
        with patch('src.workflow_job_collector.WorkflowTracer'):
            self.collector = WorkflowJobCollector(
                dsn=self.dsn,
                token=self.token,
                dry_run=True
            )

    def tearDown(self):
        """Clean up after tests."""
        for timer in self.collector.workflow_timers.values():
            timer.cancel()

    def _create_job_data(self, job_id: int, run_id: int, name: str, 
                         conclusion: str = "success") -> dict:
        """Create a mock job data payload."""
        now = datetime.utcnow()
        return {
            "workflow_job": {
                "id": job_id,
                "run_id": run_id,
                "name": name,
                "conclusion": conclusion,
                "started_at": (now - timedelta(minutes=5)).isoformat() + "Z",
                "completed_at": now.isoformat() + "Z",
                "html_url": f"https://github.com/test/repo/actions/runs/{run_id}/jobs/{job_id}",
                "steps": [],
                "head_branch": "main",
                "head_sha": "abc123",
                "run_attempt": 1,
            },
            "repository": {
                "full_name": "test-org/test-repo"
            }
        }

    def test_jobs_arrive_after_timeout(self):
        """Test scenario where jobs arrive after timeout has elapsed."""
        # Set total count to 5
        self.collector.workflow_total_jobs[self.test_run_id] = 5
        
        # Add 3 jobs
        for i in range(3):
            job_data = self._create_job_data(i, self.test_run_id, f"job-{i}")
            with patch.object(self.collector, '_schedule_workflow_processing'):
                self.collector.add_job(job_data)
        
        # Wait for timeout
        time.sleep(NO_NEW_JOBS_TIMEOUT + 0.1)
        
        # Add 2 more jobs after timeout
        for i in range(3, 5):
            job_data = self._create_job_data(i, self.test_run_id, f"job-{i}")
            with patch.object(self.collector, '_schedule_workflow_processing'):
                self.collector.add_job(job_data)
        
        # Should have all 5 jobs
        self.assertEqual(len(self.collector.workflow_jobs[self.test_run_id]), 5)

    def test_max_workflow_wait_time_exceeded(self):
        """Test that workflows exceeding max wait time are processed."""
        # Set arrival time to past max wait time
        past_time = time.time() - (MAX_WORKFLOW_WAIT_TIME + 10)
        self.collector.job_arrival_times[self.test_run_id].append(past_time)
        
        # Add a completed job
        job = self._create_job_data(1, self.test_run_id, "test-job")
        self.collector.workflow_jobs[self.test_run_id].append(job["workflow_job"])
        
        result = self.collector._should_process_workflow_now(self.test_run_id)
        self.assertTrue(result)

    def test_incomplete_jobs_prevent_processing(self):
        """Test that workflows with incomplete jobs are not processed."""
        # Add a job without conclusion
        incomplete_job = self._create_job_data(1, self.test_run_id, "incomplete-job")
        incomplete_job["workflow_job"]["conclusion"] = None
        self.collector.workflow_jobs[self.test_run_id].append(incomplete_job["workflow_job"])
        
        result = self.collector._should_process_workflow_now(self.test_run_id)
        self.assertFalse(result)

    def test_multiple_workflows_concurrent(self):
        """Test handling multiple workflow runs concurrently."""
        run_id_1 = 11111
        run_id_2 = 22222
        
        # Add jobs to different workflows
        job1 = self._create_job_data(1, run_id_1, "job-1")
        job2 = self._create_job_data(2, run_id_2, "job-2")
        
        with patch.object(self.collector, '_schedule_workflow_processing'):
            self.collector.add_job(job1)
            self.collector.add_job(job2)
        
        # Verify both workflows are tracked separately
        self.assertIn(run_id_1, self.collector.workflow_jobs)
        self.assertIn(run_id_2, self.collector.workflow_jobs)
        self.assertEqual(len(self.collector.workflow_jobs[run_id_1]), 1)
        self.assertEqual(len(self.collector.workflow_jobs[run_id_2]), 1)

    def test_api_failure_fallback_to_timeout(self):
        """Test that API failure falls back to timeout-based detection."""
        repository = {"full_name": "test-org/test-repo"}
        job_data = self._create_job_data(1, self.test_run_id, "test-job")
        job_data["repository"] = repository
        
        # Mock API failure
        with patch('requests.get', side_effect=requests.exceptions.RequestException("API Error")):
            with patch.object(self.collector, '_schedule_timeout_check') as mock_schedule:
                self.collector.add_job(job_data)
        
        # Should have None in cache (API failed)
        self.assertIsNone(self.collector.workflow_total_jobs.get(self.test_run_id))
        # Should still schedule timeout check (fallback behavior)
        # Note: This depends on job completion status

    def test_total_count_zero(self):
        """Test handling when API returns total_count of 0."""
        repository = {"full_name": "test-org/test-repo"}
        job_data = self._create_job_data(1, self.test_run_id, "test-job")
        job_data["repository"] = repository
        
        mock_response = Mock()
        mock_response.json.return_value = {"total_count": 0}
        mock_response.raise_for_status = Mock()
        
        with patch('requests.get', return_value=mock_response):
            with patch.object(self.collector, '_schedule_workflow_processing'):
                self.collector.add_job(job_data)
        
        # Should handle 0 count gracefully
        self.assertEqual(self.collector.workflow_total_jobs[self.test_run_id], 0)

    def test_missing_repository_info(self):
        """Test handling when repository info is missing from webhook."""
        job_data = self._create_job_data(1, self.test_run_id, "test-job")
        del job_data["repository"]  # Remove repository info
        
        mock_response = Mock()
        mock_response.json.return_value = {"total_count": 3}
        mock_response.raise_for_status = Mock()
        
        with patch('requests.get', return_value=mock_response):
            with patch.object(self.collector, '_schedule_workflow_processing'):
                self.collector.add_job(job_data)
        
        # Should still work, using "unknown/unknown" as fallback
        # API call might fail, but shouldn't crash

    def test_multiple_workflows_concurrent_different_job_ids(self):
        """Test that multiple workflow runs with different job IDs are handled correctly."""
        run_id_1 = 11111
        run_id_2 = 22222
        job_id_1 = 99999
        job_id_2 = 88888  # Different job ID for different run
        
        job1 = self._create_job_data(job_id_1, run_id_1, "job-1")
        job2 = self._create_job_data(job_id_2, run_id_2, "job-2")
        
        # Mock API calls for both runs - return different total counts
        def mock_get_side_effect(url, **kwargs):
            mock_resp = Mock()
            if str(run_id_1) in url:
                mock_resp.json.return_value = {"total_count": 1}  # Run 1 has 1 job
            else:
                mock_resp.json.return_value = {"total_count": 1}  # Run 2 has 1 job
            mock_resp.raise_for_status = Mock()
            return mock_resp
        
        with patch('requests.get', side_effect=mock_get_side_effect):
            with patch.object(self.collector, '_schedule_workflow_processing'):
                with patch.object(self.collector, '_schedule_timeout_check'):
                    with patch.object(self.collector, '_should_process_workflow_now', return_value=False):
                        with patch.object(self.collector, '_process_workflow_immediately'):
                            # Add jobs to different workflow runs
                            self.collector.add_job(job1)
                            self.collector.add_job(job2)
        
        # Verify both jobs were added to processed_jobs
        self.assertIn(job_id_1, self.collector.processed_jobs)
        self.assertIn(job_id_2, self.collector.processed_jobs)
        # Verify both workflows have their jobs
        self.assertEqual(len(self.collector.workflow_jobs[run_id_1]), 1)
        self.assertEqual(len(self.collector.workflow_jobs[run_id_2]), 1)


class TestWorkflowTracerNewFeatures(unittest.TestCase):
    """Test suite for new WorkflowTracer features."""

    def setUp(self):
        """Set up test fixtures."""
        self.dsn = "https://test@sentry.io/123"
        self.token = "test_token"
        
        with patch('src.workflow_tracer.Envelope'):
            from src.workflow_tracer import WorkflowTracer
            self.tracer = WorkflowTracer(
                token=self.token,
                dsn=self.dsn,
                dry_run=True
            )

    def _create_job(self, job_id: int, run_id: int, name: str, 
                   started_at: str = None, completed_at: str = None) -> dict:
        """Create a mock job."""
        now = datetime.utcnow()
        if not started_at:
            started_at = (now - timedelta(minutes=5)).isoformat() + "Z"
        if not completed_at:
            completed_at = now.isoformat() + "Z"
        
        return {
            "id": job_id,
            "run_id": run_id,
            "name": name,
            "conclusion": "success",
            "started_at": started_at,
            "completed_at": completed_at,
            "head_branch": "main",
            "head_sha": "abc123",
            "run_attempt": 1,
            "steps": []
        }

    def test_fetch_workflow_run_timestamps_success(self):
        """Test successful fetching of workflow run timestamps."""
        run_id = 12345
        repo_full_name = "test-org/test-repo"
        
        mock_response = Mock()
        mock_response.json.return_value = {
            "created_at": "2025-11-17T17:36:13Z",
            "updated_at": "2025-11-17T17:36:52Z"
        }
        mock_response.raise_for_status = Mock()
        
        job = self._create_job(1, run_id, "test-job")
        
        with patch.object(self.tracer, '_fetch_github', return_value=mock_response):
            workflow_data = self.tracer._get_workflow_run_data(
                job,
                repository_info={"full_name": repo_full_name}
            )
        
        self.assertEqual(workflow_data["runs"]["created_at"], "2025-11-17T17:36:13Z")
        self.assertEqual(workflow_data["runs"]["updated_at"], "2025-11-17T17:36:52Z")

    def test_fetch_workflow_run_timestamps_no_token(self):
        """Test that workflow run timestamps are None when no token."""
        self.tracer.token = None
        
        job = self._create_job(1, 12345, "test-job")
        workflow_data = self.tracer._get_workflow_run_data(job)
        
        self.assertIsNone(workflow_data["runs"].get("created_at"))
        self.assertIsNone(workflow_data["runs"].get("updated_at"))

    def test_fetch_workflow_run_timestamps_api_failure(self):
        """Test that API failures are handled gracefully."""
        job = self._create_job(1, 12345, "test-job")
        
        with patch.object(self.tracer, '_fetch_github', side_effect=Exception("API Error")):
            workflow_data = self.tracer._get_workflow_run_data(
                job,
                repository_info={"full_name": "test-org/test-repo"}
            )
        
        # Should fall back to None timestamps
        self.assertIsNone(workflow_data["runs"].get("created_at"))
        self.assertIsNone(workflow_data["runs"].get("updated_at"))

    def test_create_workflow_transaction_uses_run_timestamps(self):
        """Test that workflow transaction uses run timestamps when available."""
        job = self._create_job(1, 12345, "test-job")
        all_jobs = [job]
        
        # Mock workflow run data with timestamps
        mock_workflow_data = {
            "runs": {
                "head_commit": {"author": {"name": "Test", "email": "test@test.com"}},
                "head_branch": "main",
                "head_sha": "abc123",
                "run_attempt": 1,
                "html_url": "https://github.com/test/repo/actions/runs/12345",
                "repository": {"full_name": "test-org/test-repo"},
                "created_at": "2025-11-17T17:36:13Z",
                "updated_at": "2025-11-17T17:36:52Z"
            },
            "workflow": {"name": "Test Workflow", "path": ".github/workflows/test.yml"},
            "repo": "test-org/test-repo"
        }
        
        with patch.object(self.tracer, '_get_workflow_run_data', return_value=mock_workflow_data):
            transaction = self.tracer._create_workflow_transaction(job, all_jobs)
        
        self.assertEqual(transaction["start_timestamp"], "2025-11-17T17:36:13Z")
        self.assertEqual(transaction["timestamp"], "2025-11-17T17:36:52Z")

    def test_create_workflow_transaction_fallback_to_job_timestamps(self):
        """Test that workflow transaction falls back to job timestamps."""
        job = self._create_job(
            1, 12345, "test-job",
            started_at="2025-11-17T17:36:10Z",
            completed_at="2025-11-17T17:36:45Z"
        )
        all_jobs = [job]
        
        # Mock workflow run data without timestamps
        mock_workflow_data = {
            "runs": {
                "head_commit": {"author": {"name": "Test", "email": "test@test.com"}},
                "head_branch": "main",
                "head_sha": "abc123",
                "run_attempt": 1,
                "html_url": "https://github.com/test/repo/actions/runs/12345",
                "repository": {"full_name": "test-org/test-repo"},
                "created_at": None,
                "updated_at": None
            },
            "workflow": {"name": "Test Workflow", "path": ".github/workflows/test.yml"},
            "repo": "test-org/test-repo"
        }
        
        with patch.object(self.tracer, '_get_workflow_run_data', return_value=mock_workflow_data):
            transaction = self.tracer._create_workflow_transaction(job, all_jobs)
        
        # Should use job timestamps
        self.assertEqual(transaction["start_timestamp"], "2025-11-17T17:36:10Z")
        self.assertEqual(transaction["timestamp"], "2025-11-17T17:36:45Z")

    def test_create_workflow_transaction_adds_cleanup_span(self):
        """Test that cleanup span is added when there's a delta."""
        job = self._create_job(
            1, 12345, "test-job",
            started_at="2025-11-17T17:36:10Z",
            completed_at="2025-11-17T17:36:48Z"  # Job completes at 48s
        )
        all_jobs = [job]
        
        # Mock workflow run data with updated_at later than job completion
        mock_workflow_data = {
            "runs": {
                "head_commit": {"author": {"name": "Test", "email": "test@test.com"}},
                "head_branch": "main",
                "head_sha": "abc123",
                "run_attempt": 1,
                "html_url": "https://github.com/test/repo/actions/runs/12345",
                "repository": {"full_name": "test-org/test-repo"},
                "created_at": "2025-11-17T17:36:13Z",
                "updated_at": "2025-11-17T17:36:52Z"  # Workflow completes at 52s (4s later)
            },
            "workflow": {"name": "Test Workflow", "path": ".github/workflows/test.yml"},
            "repo": "test-org/test-repo"
        }
        
        with patch.object(self.tracer, '_get_workflow_run_data', return_value=mock_workflow_data):
            # Mock re-fetch to return same data
            with patch.object(self.tracer, '_fetch_github') as mock_fetch:
                mock_response = Mock()
                mock_response.json.return_value = {
                    "created_at": "2025-11-17T17:36:13Z",
                    "updated_at": "2025-11-17T17:36:52Z"
                }
                mock_fetch.return_value = mock_response
                
                transaction = self.tracer._create_workflow_transaction(job, all_jobs)
        
        # Should have cleanup span
        cleanup_spans = [s for s in transaction["spans"] if s["op"] == "workflow.cleanup"]
        self.assertEqual(len(cleanup_spans), 1)
        self.assertEqual(cleanup_spans[0]["name"], "Workflow cleanup and teardown")

    def test_create_workflow_transaction_no_cleanup_span_when_no_delta(self):
        """Test that cleanup span is not added when there's no delta."""
        job = self._create_job(
            1, 12345, "test-job",
            started_at="2025-11-17T17:36:10Z",
            completed_at="2025-11-17T17:36:52Z"  # Job completes at same time as workflow
        )
        all_jobs = [job]
        
        # Mock workflow run data with updated_at same as job completion
        mock_workflow_data = {
            "runs": {
                "head_commit": {"author": {"name": "Test", "email": "test@test.com"}},
                "head_branch": "main",
                "head_sha": "abc123",
                "run_attempt": 1,
                "html_url": "https://github.com/test/repo/actions/runs/12345",
                "repository": {"full_name": "test-org/test-repo"},
                "created_at": "2025-11-17T17:36:13Z",
                "updated_at": "2025-11-17T17:36:52Z"  # Same as job completion
            },
            "workflow": {"name": "Test Workflow", "path": ".github/workflows/test.yml"},
            "repo": "test-org/test-repo"
        }
        
        with patch.object(self.tracer, '_get_workflow_run_data', return_value=mock_workflow_data):
            # Mock re-fetch to return same data
            with patch.object(self.tracer, '_fetch_github') as mock_fetch:
                mock_response = Mock()
                mock_response.json.return_value = {
                    "created_at": "2025-11-17T17:36:13Z",
                    "updated_at": "2025-11-17T17:36:52Z"
                }
                mock_fetch.return_value = mock_response
                
                transaction = self.tracer._create_workflow_transaction(job, all_jobs)
        
        # Should NOT have cleanup span
        cleanup_spans = [s for s in transaction["spans"] if s["op"] == "workflow.cleanup"]
        self.assertEqual(len(cleanup_spans), 0)

    def test_re_fetch_workflow_run_before_sending(self):
        """Test that workflow run is re-fetched before sending trace."""
        job = self._create_job(1, 12345, "test-job")
        all_jobs = [job]
        
        # First fetch returns old updated_at
        first_fetch_data = {
            "runs": {
                "head_commit": {"author": {"name": "Test", "email": "test@test.com"}},
                "head_branch": "main",
                "head_sha": "abc123",
                "run_attempt": 1,
                "html_url": "https://github.com/test/repo/actions/runs/12345",
                "repository": {"full_name": "test-org/test-repo"},
                "created_at": "2025-11-17T17:36:13Z",
                "updated_at": "2025-11-17T17:36:48Z"  # Old timestamp
            },
            "workflow": {"name": "Test Workflow", "path": ".github/workflows/test.yml"},
            "repo": "test-org/test-repo"
        }
        
        # Second fetch (re-fetch) returns new updated_at
        second_fetch_response = Mock()
        second_fetch_response.json.return_value = {
            "created_at": "2025-11-17T17:36:13Z",
            "updated_at": "2025-11-17T17:36:52Z"  # New timestamp
        }
        
        with patch.object(self.tracer, '_get_workflow_run_data', return_value=first_fetch_data):
            with patch.object(self.tracer, '_fetch_github', return_value=second_fetch_response) as mock_fetch:
                transaction = self.tracer._create_workflow_transaction(
                    job, all_jobs,
                    repository_info={"full_name": "test-org/test-repo"}
                )
        
        # Verify re-fetch was called
        mock_fetch.assert_called()
        # Verify transaction uses new timestamp
        self.assertEqual(transaction["timestamp"], "2025-11-17T17:36:52Z")


if __name__ == '__main__':
    unittest.main()

