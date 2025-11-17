"""
Workflow Job Collector Module

This module handles the collection and aggregation of GitHub workflow jobs,
determining when a workflow is complete and triggering trace submissions.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

import requests

from .workflow_tracer import WorkflowTracer

# Configuration Constants
LOGGING_LEVEL = os.environ.get("LOGGING_LEVEL", logging.INFO)

# Timing Constants (in seconds)
SMALL_WORKFLOW_PROCESSING_DELAY = 2.0  # Delay for workflows with few jobs
NO_NEW_JOBS_TIMEOUT = 7.0  # Time to wait before assuming no more jobs
MAX_WORKFLOW_WAIT_TIME = 300.0  # Maximum time to wait for workflow completion (5 minutes)

# Feature Flags
ENABLE_HIERARCHICAL_TRACING = os.environ.get("ENABLE_HIERARCHICAL_TRACING", "true").lower() == "true"
SENTRY_ORG_ONLY = os.environ.get("HIERARCHICAL_TRACING_SENTRY_ORG_ONLY", "false").lower() == "true"

logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)


class WorkflowJobCollector:
    """
    Collects jobs from a workflow run and sends workflow-level transactions.
    
    This class aggregates jobs from GitHub workflow runs and determines when
    a workflow is complete. Once complete, it sends a single hierarchical
    trace containing all jobs and steps as spans.
    
    Attributes:
        dsn: Sentry DSN for trace submission
        token: GitHub API token
        dry_run: If True, no traces are sent
        workflow_jobs: Maps run_id to list of jobs
        processed_jobs: Set of job IDs already processed
        workflow_timers: Active timers for workflow processing
        processed_workflows: Set of workflow run IDs already sent
        job_arrival_times: Tracks when jobs arrive for smart detection
    """

    def __init__(self, dsn: str, token: Optional[str], dry_run: bool = False):
        """
        Initialize the WorkflowJobCollector.
        
        Args:
            dsn: Sentry DSN for trace submission
            token: GitHub API token for fetching workflow data
            dry_run: If True, simulates operations without sending traces
        """
        self.dsn = dsn
        self.token = token
        self.dry_run = dry_run
        
        # State tracking
        self.workflow_jobs: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        self.workflow_repositories: Dict[int, Dict[str, Any]] = {}  # run_id -> repository info
        self.processed_jobs: set[int] = set()
        self.processed_workflows: set[int] = set()
        self.job_arrival_times: Dict[int, List[float]] = defaultdict(list)
        self.workflow_timers: Dict[int, threading.Timer] = {}
        self.workflow_total_jobs: Dict[int, Optional[int]] = {}  # run_id -> total_count (None = not fetched yet)
        
        # Thread safety
        self._lock = threading.Lock()
        
        # Initialize workflow tracer
        self.workflow_tracer = WorkflowTracer(token, dsn, dry_run)
        
        logger.info(
            f"WorkflowJobCollector initialized (dry_run={dry_run}, "
            f"hierarchical_tracing={ENABLE_HIERARCHICAL_TRACING})"
        )

    def add_job(self, job_data: Dict[str, Any]) -> None:
        """
        Add a job to the collector and check if workflow is complete.
        
        Args:
            job_data: GitHub webhook job payload
        """
        job = job_data["workflow_job"]
        run_id = job["run_id"]
        job_id = job["id"]
        
        with self._lock:
            if self._is_job_already_processed(job_id):
                return
            
            # Store repository info from webhook payload if available
            if run_id not in self.workflow_repositories and "repository" in job_data:
                self.workflow_repositories[run_id] = job_data["repository"]
            
            # Fetch total job count from GitHub API when first job arrives
            if run_id not in self.workflow_total_jobs:
                repo_full_name = "unknown/unknown"
                if run_id in self.workflow_repositories:
                    repo_full_name = self.workflow_repositories[run_id].get("full_name", repo_full_name)
                elif "repository" in job_data:
                    repo_full_name = job_data["repository"].get("full_name", repo_full_name)
                
                total_count = self._fetch_total_job_count(run_id, repo_full_name)
                self.workflow_total_jobs[run_id] = total_count
            
            self._record_job(run_id, job_id, job)
            
            # Check if we should process now or schedule for later
            if self._should_process_workflow_now(run_id):
                self._schedule_workflow_processing(run_id)
            elif self._should_schedule_timeout_check(run_id):
                # All jobs complete but timeout hasn't elapsed - schedule a check after timeout
                self._schedule_timeout_check(run_id)

    def _is_job_already_processed(self, job_id: int) -> bool:
        """Check if a job has already been processed."""
        if job_id in self.processed_jobs:
            logger.debug(f"Job {job_id} already processed, skipping")
            return True
        return False

    def _record_job(self, run_id: int, job_id: int, job: Dict[str, Any]) -> None:
        """Record a new job arrival."""
        self.processed_jobs.add(job_id)
        self.workflow_jobs[run_id].append(job)
        self.job_arrival_times[run_id].append(time.time())
        
        logger.info(
            f"Added job '{job['name']}' (ID: {job_id}) to workflow run {run_id} "
            f"(total jobs: {len(self.workflow_jobs[run_id])})"
        )

    def _fetch_total_job_count(self, run_id: int, repo_full_name: str) -> Optional[int]:
        """
        Fetch the total number of jobs for a workflow run from GitHub API.
        
        Args:
            run_id: Workflow run ID
            repo_full_name: Repository full name (e.g., "owner/repo")
            
        Returns:
            Total number of jobs, or None if fetch fails or token is missing
        """
        if not self.token:
            logger.debug(f"No GitHub token available, cannot fetch total job count for run {run_id}")
            return None
        
        try:
            # GitHub API endpoint: GET /repos/{owner}/{repo}/actions/runs/{run_id}/jobs
            api_url = f"https://api.github.com/repos/{repo_full_name}/actions/runs/{run_id}/jobs"
            headers = {"Authorization": f"token {self.token}"}
            
            logger.debug(f"Fetching total job count for workflow run {run_id} from GitHub API")
            response = requests.get(api_url, headers=headers, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            total_count = data.get("total_count")
            
            if total_count is not None:
                logger.info(
                    f"Fetched total job count for workflow run {run_id}: {total_count} jobs"
                )
                return total_count
            else:
                logger.warning(
                    f"GitHub API response missing 'total_count' for workflow run {run_id}"
                )
                return None
                
        except requests.exceptions.RequestException as e:
            logger.warning(
                f"Failed to fetch total job count for workflow run {run_id}: {e}. "
                "Will fall back to timeout-based detection."
            )
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error fetching total job count for workflow run {run_id}: {e}",
                exc_info=True
            )
            return None

    def _should_process_workflow_now(self, run_id: int) -> bool:
        """
        Determine if a workflow should be processed now.
        
        Uses smart detection based on:
        - Job completion status
        - Number of jobs
        - Time since last job arrival
        - Maximum wait time
        
        Args:
            run_id: Workflow run ID
            
        Returns:
            True if workflow should be processed, False otherwise
        """
        if run_id in self.processed_workflows:
            logger.debug(f"Workflow {run_id} already processed")
            return False
        
        jobs = self.workflow_jobs[run_id]
        jobs_count = len(jobs)
        
        # Check if all jobs are completed
        if not self._all_jobs_completed(jobs):
            incomplete_jobs = [j.get("name") for j in jobs if j.get("conclusion") is None]
            logger.debug(f"Workflow {run_id} has {jobs_count} jobs, {len(incomplete_jobs)} incomplete: {incomplete_jobs}")
            return False
        
        # Check if we know the total job count and if we have all jobs
        total_count = self.workflow_total_jobs.get(run_id)
        if total_count is not None:
            # We have the total count from API, check if we've received all jobs
            if jobs_count >= total_count:
                logger.info(
                    f"Workflow {run_id} has all {total_count} jobs (received {jobs_count}), "
                    "ready to process"
                )
                # Still need to wait for timeout to ensure all jobs are complete
                return self._meets_processing_threshold(run_id, jobs_count)
            else:
                logger.debug(
                    f"Workflow {run_id} has {jobs_count}/{total_count} jobs, "
                    "waiting for more jobs to arrive"
                )
                return False
        # If total_count is None, fall back to timeout-based detection
        
        # Check if maximum wait time exceeded
        if self._is_workflow_timeout_exceeded(run_id):
            logger.warning(
                f"Workflow {run_id} exceeded maximum wait time "
                f"({MAX_WORKFLOW_WAIT_TIME}s), processing with {jobs_count} jobs"
            )
            return True
        
        # Determine based on workflow size
        return self._meets_processing_threshold(run_id, jobs_count)

    def _all_jobs_completed(self, jobs: List[Dict[str, Any]]) -> bool:
        """Check if all jobs in a list are completed."""
        return all(job.get("conclusion") is not None for job in jobs)

    def _is_workflow_timeout_exceeded(self, run_id: int) -> bool:
        """Check if the workflow has exceeded the maximum wait time."""
        arrival_times = self.job_arrival_times[run_id]
        if not arrival_times:
            return False
        
        first_arrival = arrival_times[0]
        time_elapsed = time.time() - first_arrival
        return time_elapsed > MAX_WORKFLOW_WAIT_TIME

    def _meets_processing_threshold(self, run_id: int, jobs_count: int) -> bool:
        """
        Check if the workflow meets the processing threshold.
        
        Always waits for the timeout to ensure all jobs are collected before processing.
        This prevents sending incomplete traces when jobs arrive at different times.
        
        Args:
            run_id: Workflow run ID
            jobs_count: Number of jobs in the workflow
            
        Returns:
            True if timeout elapsed and we should process, False otherwise
        """
        # Always wait for timeout to ensure we collect all jobs
        # Jobs can arrive at different times, so we need to wait for the timeout
        # before assuming no more jobs will arrive
        return self._has_job_arrival_timeout_elapsed(run_id, jobs_count)

    def _has_job_arrival_timeout_elapsed(self, run_id: int, jobs_count: int) -> bool:
        """
        Check if enough time has passed since the last job arrival.
        
        Args:
            run_id: Workflow run ID
            jobs_count: Number of jobs in the workflow
            
        Returns:
            True if timeout elapsed, False otherwise
        """
        arrival_times = self.job_arrival_times[run_id]
        
        # Always wait for timeout to ensure we collect all jobs
        # Don't immediately process single-job workflows as they might be multi-job
        if len(arrival_times) >= 1:
            time_since_last_job = time.time() - arrival_times[-1]
            if time_since_last_job > NO_NEW_JOBS_TIMEOUT:
                logger.info(
                    f"No new jobs for {time_since_last_job:.1f}s "
                    f"(threshold: {NO_NEW_JOBS_TIMEOUT}s), processing {jobs_count} job(s)"
                )
                return True
        
        return False

    def _should_schedule_timeout_check(self, run_id: int) -> bool:
        """
        Check if we should schedule a timeout check.
        
        This is called when all jobs are complete but the timeout hasn't elapsed yet.
        We need to schedule a timer to check again after the timeout period.
        
        Args:
            run_id: Workflow run ID
            
        Returns:
            True if we should schedule a timeout check, False otherwise
        """
        if run_id in self.processed_workflows:
            return False
        
        jobs = self.workflow_jobs[run_id]
        if not self._all_jobs_completed(jobs):
            return False
        
        # Check if we know the total job count and if we have all jobs
        total_count = self.workflow_total_jobs.get(run_id)
        if total_count is not None:
            jobs_count = len(jobs)
            if jobs_count < total_count:
                # We haven't received all jobs yet, don't schedule timeout check
                logger.debug(
                    f"Workflow {run_id} has {jobs_count}/{total_count} jobs, "
                    "not scheduling timeout check yet"
                )
                return False
            # We have all jobs, proceed with timeout check scheduling
        
        # Check if timeout hasn't elapsed yet
        arrival_times = self.job_arrival_times[run_id]
        if len(arrival_times) >= 1:
            time_since_last_job = time.time() - arrival_times[-1]
            if time_since_last_job <= NO_NEW_JOBS_TIMEOUT:
                # Timeout hasn't elapsed, and we don't already have a timer scheduled
                if run_id not in self.workflow_timers:
                    return True
        
        return False

    def _schedule_timeout_check(self, run_id: int) -> None:
        """
        Schedule a check after the timeout period to process the workflow.
        
        Args:
            run_id: Workflow run ID
        """
        arrival_times = self.job_arrival_times[run_id]
        if not arrival_times:
            return
        
        time_since_last_job = time.time() - arrival_times[-1]
        remaining_time = NO_NEW_JOBS_TIMEOUT - time_since_last_job
        
        if remaining_time > 0:
            logger.info(
                f"Scheduling timeout check for workflow {run_id} "
                f"in {remaining_time:.1f}s (timeout: {NO_NEW_JOBS_TIMEOUT}s)"
            )
            
            timer = threading.Timer(
                remaining_time,
                self._process_workflow_immediately,
                args=[run_id]
            )
            self.workflow_timers[run_id] = timer
            timer.start()

    def _schedule_workflow_processing(self, run_id: int) -> None:
        """Schedule workflow processing with a short delay to collect all jobs."""
        jobs_count = len(self.workflow_jobs[run_id])
        
        logger.info(
            f"Scheduling workflow {run_id} for processing "
            f"(jobs: {jobs_count}, delay: {SMALL_WORKFLOW_PROCESSING_DELAY}s)"
        )
        
        timer = threading.Timer(
            SMALL_WORKFLOW_PROCESSING_DELAY,
            self._process_workflow_immediately,
            args=[run_id]
        )
        self.workflow_timers[run_id] = timer
        timer.start()

    def _process_workflow_immediately(self, run_id: int) -> None:
        """
        Process workflow immediately when triggered by timer.
        
        This method is called by a timer thread and includes exception
        handling to prevent silent failures and resource leaks.
        
        Args:
            run_id: Workflow run ID to process
        """
        try:
            with self._lock:
                if not self._should_process_workflow(run_id):
                    return
                
                jobs = self.workflow_jobs[run_id]
                logger.info(
                    f"Processing workflow run {run_id} with {len(jobs)} jobs"
                )
                
                if self._all_jobs_completed(jobs):
                    logger.info(
                        f"All {len(jobs)} jobs complete for workflow {run_id}, sending trace"
                    )
                    self._send_workflow_trace(run_id)
                else:
                    logger.warning(
                        f"Not all jobs complete for workflow {run_id}, skipping"
                    )
        except Exception as e:
            logger.error(
                f"Error processing workflow run {run_id}: {e}",
                exc_info=True
            )
            # Ensure cleanup happens even if there's an exception
            self._cleanup_workflow_run(run_id)

    def _should_process_workflow(self, run_id: int) -> bool:
        """Check if a workflow should be processed (not already processed)."""
        if run_id in self.processed_workflows:
            logger.debug(f"Workflow run {run_id} already processed, skipping")
            return False
        
        if not self.workflow_jobs[run_id]:
            logger.warning(f"No jobs found for workflow run {run_id}")
            return False
        
        return True

    def _send_workflow_trace(self, run_id: int) -> None:
        """
        Send workflow-level trace for all jobs in the run.
        
        Args:
            run_id: Workflow run ID to send trace for
        """
        if run_id in self.processed_workflows:
            logger.warning(
                f"Workflow run {run_id} already processed, "
                "skipping to prevent duplicates"
            )
            return
        
        jobs = self.workflow_jobs[run_id]
        if not jobs:
            logger.warning(f"No jobs found for workflow run {run_id}")
            return
        
        logger.info(
            f"Sending workflow trace for run {run_id} with {len(jobs)} jobs"
        )
        
        try:
            base_job = jobs[0]
            # Pass repository info if available
            repository_info = self.workflow_repositories.get(run_id)
            self.workflow_tracer.send_workflow_trace(base_job, jobs, repository_info=repository_info)
            logger.info(
                f"Successfully sent workflow trace for run {run_id}"
            )
        except Exception as e:
            logger.error(
                f"Failed to send workflow trace for run {run_id}: {e}",
                exc_info=True
            )
            logger.warning(
                "NOT falling back to individual traces to prevent duplicates"
            )
        finally:
            self._cleanup_workflow_run(run_id)

    def _cleanup_workflow_run(self, run_id: int) -> None:
        """
        Clean up workflow run data to prevent resource leaks.
        
        This method should always be called after processing a workflow,
        whether successful or not, to ensure proper cleanup.
        
        Args:
            run_id: Workflow run ID to clean up
        """
        try:
            with self._lock:
                self.processed_workflows.add(run_id)
                
                if run_id in self.workflow_jobs:
                    del self.workflow_jobs[run_id]
                
                if run_id in self.workflow_timers:
                    self.workflow_timers[run_id].cancel()
                    del self.workflow_timers[run_id]
                
                if run_id in self.job_arrival_times:
                    del self.job_arrival_times[run_id]
                
                if run_id in self.workflow_repositories:
                    del self.workflow_repositories[run_id]
                
                if run_id in self.workflow_total_jobs:
                    del self.workflow_total_jobs[run_id]
                
                logger.debug(f"Cleaned up workflow run {run_id}")
        except Exception as cleanup_error:
            logger.error(
                f"Error during cleanup of workflow run {run_id}: {cleanup_error}",
                exc_info=True
            )

    def is_hierarchical_tracing_enabled(self, org: str) -> bool:
        """
        Check if hierarchical tracing is enabled for an organization.
        
        Args:
            org: GitHub organization name
            
        Returns:
            True if hierarchical tracing should be used, False otherwise
        """
        if not ENABLE_HIERARCHICAL_TRACING:
            return False
        
        if SENTRY_ORG_ONLY and org.lower() != "getsentry":
            logger.debug(
                f"Hierarchical tracing disabled for org '{org}' "
                "(SENTRY_ORG_ONLY mode enabled)"
            )
            return False
        
        return True





