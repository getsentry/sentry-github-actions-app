"""
Tests for WorkflowJobCollector module.

This module tests the collection and aggregation of GitHub workflow jobs,
including workflow completion detection, timeout handling, and thread safety.
"""

import os
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.workflow_job_collector import (
    WorkflowJobCollector,
    SMALL_WORKFLOW_PROCESSING_DELAY,
    NO_NEW_JOBS_TIMEOUT,
    MAX_WORKFLOW_WAIT_TIME,
    LARGE_WORKFLOW_THRESHOLD,
    MEDIUM_WORKFLOW_THRESHOLD,
    SMALL_WORKFLOW_THRESHOLD,
)


class TestWorkflowJobCollector(unittest.TestCase):
    """Test suite for WorkflowJobCollector class."""

    def setUp(self):
        """Set up test fixtures."""
        self.dsn = "https://test@sentry.io/123"
        self.token = "test_token"
        self.test_run_id = 12345
        
        # Mock the WorkflowTracer to avoid actual API calls
        with patch('src.workflow_job_collector.WorkflowTracer'):
            self.collector = WorkflowJobCollector(
                dsn=self.dsn,
                token=self.token,
                dry_run=True
            )

    def tearDown(self):
        """Clean up after tests."""
        # Cancel any active timers
        for timer in self.collector.workflow_timers.values():
            timer.cancel()

    def _create_job_data(self, job_id: int, run_id: int, name: str, 
                         conclusion: str = "success") -> dict:
        """
        Create a mock job data payload.
        
        Args:
            job_id: Unique job identifier
            run_id: Workflow run identifier
            name: Job name
            conclusion: Job conclusion (success, failure, cancelled, etc.)
            
        Returns:
            Mock job data dictionary
        """
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
                "steps": [
                    {
                        "name": "Setup",
                        "number": 1,
                        "conclusion": "success",
                        "started_at": (now - timedelta(minutes=5)).isoformat() + "Z",
                        "completed_at": (now - timedelta(minutes=4)).isoformat() + "Z",
                    }
                ],
                "head_branch": "main",
                "head_sha": "abc123",
                "run_attempt": 1,
                "workflow_name": "Test Workflow"
            }
        }

    def test_init(self):
        """Test WorkflowJobCollector initialization."""
        self.assertEqual(self.collector.dsn, self.dsn)
        self.assertEqual(self.collector.token, self.token)
        self.assertTrue(self.collector.dry_run)
        self.assertEqual(len(self.collector.workflow_jobs), 0)
        self.assertEqual(len(self.collector.processed_jobs), 0)
        self.assertEqual(len(self.collector.processed_workflows), 0)

    def test_add_job_single(self):
        """Test adding a single job."""
        job_data = self._create_job_data(1, self.test_run_id, "test-job")
        
        with patch.object(self.collector, '_schedule_workflow_processing') as mock_schedule:
            self.collector.add_job(job_data)
        
        # Verify job was added
        self.assertIn(self.test_run_id, self.collector.workflow_jobs)
        self.assertEqual(len(self.collector.workflow_jobs[self.test_run_id]), 1)
        self.assertIn(1, self.collector.processed_jobs)
        
        # Verify scheduling was called for completed job
        mock_schedule.assert_called_once_with(self.test_run_id)

    def test_add_job_duplicate(self):
        """Test that duplicate jobs are ignored."""
        job_data = self._create_job_data(1, self.test_run_id, "test-job")
        
        with patch.object(self.collector, '_schedule_workflow_processing'):
            self.collector.add_job(job_data)
            initial_count = len(self.collector.workflow_jobs[self.test_run_id])
            
            # Add same job again
            self.collector.add_job(job_data)
            final_count = len(self.collector.workflow_jobs[self.test_run_id])
        
        # Count should not increase
        self.assertEqual(initial_count, final_count)

    def test_add_multiple_jobs(self):
        """Test adding multiple jobs to the same workflow run."""
        jobs = [
            self._create_job_data(1, self.test_run_id, "job-1"),
            self._create_job_data(2, self.test_run_id, "job-2"),
            self._create_job_data(3, self.test_run_id, "job-3"),
        ]
        
        with patch.object(self.collector, '_schedule_workflow_processing'):
            for job_data in jobs:
                self.collector.add_job(job_data)
        
        # Verify all jobs were added
        self.assertEqual(len(self.collector.workflow_jobs[self.test_run_id]), 3)
        self.assertEqual(len(self.collector.processed_jobs), 3)

    def test_all_jobs_completed(self):
        """Test detection of all jobs being completed."""
        completed_jobs = [
            {"conclusion": "success"},
            {"conclusion": "failure"},
            {"conclusion": "cancelled"},
        ]
        self.assertTrue(self.collector._all_jobs_completed(completed_jobs))
        
        incomplete_jobs = [
            {"conclusion": "success"},
            {"conclusion": None},  # Not completed
        ]
        self.assertFalse(self.collector._all_jobs_completed(incomplete_jobs))

    def test_meets_processing_threshold_large_workflow(self):
        """Test threshold detection for large workflows (10+ jobs)."""
        # Add 10 completed jobs
        for i in range(LARGE_WORKFLOW_THRESHOLD):
            job = self._create_job_data(i, self.test_run_id, f"job-{i}")
            self.collector.workflow_jobs[self.test_run_id].append(
                job["workflow_job"]
            )
            self.collector.job_arrival_times[self.test_run_id].append(time.time())
        
        result = self.collector._meets_processing_threshold(
            self.test_run_id,
            LARGE_WORKFLOW_THRESHOLD
        )
        self.assertTrue(result)

    def test_meets_processing_threshold_medium_workflow(self):
        """Test threshold detection for medium workflows (5-9 jobs)."""
        # Add 5 completed jobs
        for i in range(MEDIUM_WORKFLOW_THRESHOLD):
            job = self._create_job_data(i, self.test_run_id, f"job-{i}")
            self.collector.workflow_jobs[self.test_run_id].append(
                job["workflow_job"]
            )
            self.collector.job_arrival_times[self.test_run_id].append(time.time())
        
        result = self.collector._meets_processing_threshold(
            self.test_run_id,
            MEDIUM_WORKFLOW_THRESHOLD
        )
        self.assertTrue(result)

    def test_meets_processing_threshold_small_workflow(self):
        """Test threshold detection for small workflows (3-4 jobs)."""
        # Add 3 completed jobs
        for i in range(SMALL_WORKFLOW_THRESHOLD):
            job = self._create_job_data(i, self.test_run_id, f"job-{i}")
            self.collector.workflow_jobs[self.test_run_id].append(
                job["workflow_job"]
            )
            self.collector.job_arrival_times[self.test_run_id].append(time.time())
        
        result = self.collector._meets_processing_threshold(
            self.test_run_id,
            SMALL_WORKFLOW_THRESHOLD
        )
        self.assertTrue(result)

    def test_meets_processing_threshold_single_job(self):
        """Test threshold detection for single job workflows."""
        job = self._create_job_data(1, self.test_run_id, "single-job")
        self.collector.workflow_jobs[self.test_run_id].append(
            job["workflow_job"]
        )
        self.collector.job_arrival_times[self.test_run_id].append(time.time())
        
        result = self.collector._meets_processing_threshold(self.test_run_id, 1)
        self.assertTrue(result)

    def test_workflow_timeout_exceeded(self):
        """Test detection of workflow timeout."""
        # Set arrival time to past the timeout
        past_time = time.time() - (MAX_WORKFLOW_WAIT_TIME + 10)
        self.collector.job_arrival_times[self.test_run_id].append(past_time)
        
        result = self.collector._is_workflow_timeout_exceeded(self.test_run_id)
        self.assertTrue(result)

    def test_workflow_timeout_not_exceeded(self):
        """Test that workflow timeout is not triggered prematurely."""
        # Set arrival time to recent
        self.collector.job_arrival_times[self.test_run_id].append(time.time())
        
        result = self.collector._is_workflow_timeout_exceeded(self.test_run_id)
        self.assertFalse(result)

    def test_cleanup_workflow_run(self):
        """Test workflow run cleanup."""
        # Add some data
        job = self._create_job_data(1, self.test_run_id, "test-job")
        self.collector.workflow_jobs[self.test_run_id].append(job["workflow_job"])
        self.collector.job_arrival_times[self.test_run_id].append(time.time())
        
        # Create a mock timer
        mock_timer = Mock()
        self.collector.workflow_timers[self.test_run_id] = mock_timer
        
        # Cleanup
        self.collector._cleanup_workflow_run(self.test_run_id)
        
        # Verify cleanup
        self.assertNotIn(self.test_run_id, self.collector.workflow_jobs)
        self.assertNotIn(self.test_run_id, self.collector.job_arrival_times)
        self.assertNotIn(self.test_run_id, self.collector.workflow_timers)
        self.assertIn(self.test_run_id, self.collector.processed_workflows)
        mock_timer.cancel.assert_called_once()

    def test_send_workflow_trace_success(self):
        """Test successful workflow trace sending."""
        # Add a completed job
        job = self._create_job_data(1, self.test_run_id, "test-job")
        self.collector.workflow_jobs[self.test_run_id].append(job["workflow_job"])
        
        # Mock the workflow tracer
        with patch.object(self.collector.workflow_tracer, 'send_workflow_trace') as mock_send:
            self.collector._send_workflow_trace(self.test_run_id)
        
        # Verify trace was sent
        mock_send.assert_called_once()
        
        # Verify cleanup
        self.assertNotIn(self.test_run_id, self.collector.workflow_jobs)
        self.assertIn(self.test_run_id, self.collector.processed_workflows)

    def test_send_workflow_trace_already_processed(self):
        """Test that already processed workflows are not sent again."""
        # Mark as already processed
        self.collector.processed_workflows.add(self.test_run_id)
        
        # Add a job
        job = self._create_job_data(1, self.test_run_id, "test-job")
        self.collector.workflow_jobs[self.test_run_id].append(job["workflow_job"])
        
        # Mock the workflow tracer
        with patch.object(self.collector.workflow_tracer, 'send_workflow_trace') as mock_send:
            self.collector._send_workflow_trace(self.test_run_id)
        
        # Verify trace was NOT sent
        mock_send.assert_not_called()

    def test_send_workflow_trace_error_handling(self):
        """Test error handling during trace sending."""
        # Add a completed job
        job = self._create_job_data(1, self.test_run_id, "test-job")
        self.collector.workflow_jobs[self.test_run_id].append(job["workflow_job"])
        
        # Mock the workflow tracer to raise an exception
        with patch.object(self.collector.workflow_tracer, 'send_workflow_trace') as mock_send:
            mock_send.side_effect = Exception("Test error")
            
            # Should not raise, but should log error
            self.collector._send_workflow_trace(self.test_run_id)
        
        # Verify cleanup still happened
        self.assertNotIn(self.test_run_id, self.collector.workflow_jobs)
        self.assertIn(self.test_run_id, self.collector.processed_workflows)

    def test_process_workflow_immediately_with_complete_jobs(self):
        """Test immediate processing of workflow with all jobs complete."""
        # Add completed jobs
        for i in range(3):
            job = self._create_job_data(i, self.test_run_id, f"job-{i}")
            self.collector.workflow_jobs[self.test_run_id].append(
                job["workflow_job"]
            )
        
        # Mock the send method
        with patch.object(self.collector, '_send_workflow_trace') as mock_send:
            self.collector._process_workflow_immediately(self.test_run_id)
        
        # Verify workflow was sent
        mock_send.assert_called_once_with(self.test_run_id)

    def test_process_workflow_immediately_with_incomplete_jobs(self):
        """Test that workflows with incomplete jobs are not processed."""
        # Add a job without conclusion (incomplete)
        job_data = self._create_job_data(1, self.test_run_id, "incomplete-job")
        job_data["workflow_job"]["conclusion"] = None
        self.collector.workflow_jobs[self.test_run_id].append(
            job_data["workflow_job"]
        )
        
        # Mock the send method
        with patch.object(self.collector, '_send_workflow_trace') as mock_send:
            self.collector._process_workflow_immediately(self.test_run_id)
        
        # Verify workflow was NOT sent
        mock_send.assert_not_called()

    def test_process_workflow_immediately_exception_handling(self):
        """Test exception handling in immediate processing."""
        # Add a job
        job = self._create_job_data(1, self.test_run_id, "test-job")
        self.collector.workflow_jobs[self.test_run_id].append(job["workflow_job"])
        
        # Mock _send_workflow_trace to raise exception
        with patch.object(self.collector, '_send_workflow_trace') as mock_send:
            mock_send.side_effect = Exception("Test error")
            
            # Should handle exception gracefully
            self.collector._process_workflow_immediately(self.test_run_id)
        
        # Verify cleanup happened via exception handler
        self.assertIn(self.test_run_id, self.collector.processed_workflows)

    @patch('src.workflow_job_collector.ENABLE_HIERARCHICAL_TRACING', True)
    def test_hierarchical_tracing_enabled(self):
        """Test hierarchical tracing is enabled when feature flag is true."""
        with patch('src.workflow_job_collector.WorkflowTracer'):
            collector = WorkflowJobCollector(self.dsn, self.token, dry_run=True)
            self.assertTrue(collector.is_hierarchical_tracing_enabled("test-org"))

    @patch('src.workflow_job_collector.ENABLE_HIERARCHICAL_TRACING', False)
    def test_hierarchical_tracing_disabled(self):
        """Test hierarchical tracing is disabled when feature flag is false."""
        with patch('src.workflow_job_collector.WorkflowTracer'):
            collector = WorkflowJobCollector(self.dsn, self.token, dry_run=True)
            self.assertFalse(collector.is_hierarchical_tracing_enabled("test-org"))

    @patch('src.workflow_job_collector.ENABLE_HIERARCHICAL_TRACING', True)
    @patch('src.workflow_job_collector.SENTRY_ORG_ONLY', True)
    def test_hierarchical_tracing_sentry_org_only(self):
        """Test hierarchical tracing restricted to Sentry org."""
        with patch('src.workflow_job_collector.WorkflowTracer'):
            collector = WorkflowJobCollector(self.dsn, self.token, dry_run=True)
            
            # Should be enabled for getsentry
            self.assertTrue(collector.is_hierarchical_tracing_enabled("getsentry"))
            
            # Should be disabled for other orgs
            self.assertFalse(collector.is_hierarchical_tracing_enabled("test-org"))

    def test_thread_safety_concurrent_job_additions(self):
        """Test thread safety when adding jobs concurrently."""
        import threading
        
        def add_jobs(start_id):
            for i in range(10):
                job_data = self._create_job_data(
                    start_id + i,
                    self.test_run_id,
                    f"job-{start_id + i}"
                )
                with patch.object(self.collector, '_schedule_workflow_processing'):
                    self.collector.add_job(job_data)
        
        # Create multiple threads adding jobs
        threads = []
        for i in range(3):
            thread = threading.Thread(target=add_jobs, args=(i * 10,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify all 30 jobs were added without race conditions
        self.assertEqual(len(self.collector.processed_jobs), 30)


class TestWorkflowJobCollectorIntegration(unittest.TestCase):
    """Integration tests for WorkflowJobCollector."""

    def setUp(self):
        """Set up test fixtures."""
        self.dsn = "https://test@sentry.io/123"
        self.token = "test_token"
        
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

    def test_full_workflow_lifecycle(self):
        """Test complete workflow lifecycle from job addition to trace sending."""
        run_id = 99999
        
        # Create multiple jobs
        jobs = [
            {
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
                }
            }
            for i in range(5)
        ]
        
        # Mock the workflow tracer
        with patch.object(self.collector.workflow_tracer, 'send_workflow_trace') as mock_send:
            # Add all jobs
            for job_data in jobs:
                self.collector.add_job(job_data)
            
            # Wait for timer to fire (plus a bit extra)
            time.sleep(SMALL_WORKFLOW_PROCESSING_DELAY + 0.5)
        
        # Verify trace was sent
        mock_send.assert_called_once()
        
        # Verify cleanup
        self.assertNotIn(run_id, self.collector.workflow_jobs)
        self.assertIn(run_id, self.collector.processed_workflows)


if __name__ == '__main__':
    unittest.main()

