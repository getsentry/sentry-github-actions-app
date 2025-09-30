"""
Enhanced web app handler that creates workflow-level transactions
"""

from __future__ import annotations

import base64
import hmac
import logging
import os
import time
from typing import NamedTuple, Dict, List, Any
from collections import defaultdict

from github_app import GithubAppToken
from github_sdk import GithubClient
from workflow_tracer import WorkflowTracer
from sentry_config import fetch_dsn_for_github_org

LOGGING_LEVEL = os.environ.get("LOGGING_LEVEL", logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)


class WorkflowJobCollector:
    """Collects jobs from a workflow run and sends workflow-level transactions"""
    
    def __init__(self, dsn: str, token: str, dry_run: bool = False):
        self.dsn = dsn
        self.token = token
        self.dry_run = dry_run
        self.workflow_jobs = defaultdict(list)  # run_id -> list of jobs
        self.workflow_tracer = WorkflowTracer(token, dsn, dry_run)
        self.processed_jobs = set()  # Track processed job IDs to avoid duplicates
        
    def add_job(self, job_data: Dict[str, Any]):
        """Add a job to the collector"""
        job = job_data["workflow_job"]
        run_id = job["run_id"]
        job_id = job["id"]
        
        # Skip if we've already processed this job
        if job_id in self.processed_jobs:
            return
            
        self.processed_jobs.add(job_id)
        self.workflow_jobs[run_id].append(job)
        
        logger.info(f"Added job {job['name']} (ID: {job_id}) to workflow run {run_id}")
        
        # Check if this is the last job in the workflow
        if self._is_workflow_complete(run_id, job):
            self._send_workflow_trace(run_id)
    
    def _is_workflow_complete(self, run_id: int, current_job: Dict[str, Any]) -> bool:
        """Check if all jobs in the workflow are complete"""
        jobs = self.workflow_jobs[run_id]
        
        # If we have jobs, check if they're all completed
        if jobs:
            all_completed = all(job.get("conclusion") is not None for job in jobs)
            if all_completed:
                logger.info(f"Workflow run {run_id} appears complete with {len(jobs)} jobs")
                return True
        
        return False
    
    def _send_workflow_trace(self, run_id: int):
        """Send workflow-level trace for all jobs in the run"""
        jobs = self.workflow_jobs[run_id]
        
        if not jobs:
            return
            
        logger.info(f"Sending workflow trace for run {run_id} with {len(jobs)} jobs")
        
        try:
            # Use the first job as the base for workflow metadata
            base_job = jobs[0]
            
            # Send workflow trace
            self.workflow_tracer.send_workflow_trace(base_job, jobs)
            
            # Clean up processed jobs
            del self.workflow_jobs[run_id]
            
            logger.info(f"Successfully sent workflow trace for run {run_id}")
            
        except Exception as e:
            logger.error(f"Failed to send workflow trace for run {run_id}: {e}")
            # Fall back to individual job traces
            self._send_individual_traces(jobs)
    
    def _send_individual_traces(self, jobs: List[Dict[str, Any]]):
        """DISABLED: Individual job traces are now handled by WorkflowTracer"""
        logger.info(f"DISABLED: Individual traces for {len(jobs)} jobs - now handled by WorkflowTracer")
        return


class EnhancedWebAppHandler:
    """Enhanced web app handler with workflow-level tracing"""
    
    def __init__(self, dry_run=False):
        self.config = init_config()
        self.dry_run = dry_run
        self.job_collectors = {}  # org -> WorkflowJobCollector
        
    def _get_job_collector(self, org: str, token: str, dsn: str) -> WorkflowJobCollector:
        """Get or create a job collector for the organization"""
        if org not in self.job_collectors:
            self.job_collectors[org] = WorkflowJobCollector(dsn, token, self.dry_run)
        return self.job_collectors[org]
    
    def handle_event(self, data, headers):
        """Handle GitHub webhook events"""
        # We return 200 to make webhook not turn red since everything got processed well
        http_code = 200
        reason = "OK"

        if headers["X-GitHub-Event"] != "workflow_job":
            reason = "Event not supported."
        elif data["action"] != "completed":
            reason = "We cannot do anything with this workflow state."
        else:
            # For now, this simplifies testing
            if self.dry_run:
                return reason, http_code

            installation_id = data["installation"]["id"]
            org = data["repository"]["owner"]["login"]

            # We are executing in Github App mode
            if self.config.gh_app:
                with GithubAppToken(**self.config.gh_app._asdict()).get_token(
                    installation_id
                ) as token:
                    # Once the Sentry org has a .sentry repo we can remove the DSN from the deployment
                    dsn = fetch_dsn_for_github_org(org, token)
                    
                    # Get job collector for this org
                    collector = self._get_job_collector(org, token, dsn)
                    
                    # Add job to collector (will send workflow trace when complete)
                    collector.add_job(data)
                    
            else:
                # Once the Sentry org has a .sentry repo we can remove the DSN from the deployment
                dsn = fetch_dsn_for_github_org(org, token)
                
                # Get job collector for this org
                collector = self._get_job_collector(org, self.config.gh.token, dsn)
                
                # Add job to collector (will send workflow trace when complete)
                collector.add_job(data)

        return reason, http_code

    def valid_signature(self, body, headers):
        """Validate webhook signature"""
        if not self.config.gh.webhook_secret:
            return True
        else:
            signature = headers["X-Hub-Signature-256"].replace("sha256=", "")
            body_signature = hmac.new(
                self.config.gh.webhook_secret.encode(),
                msg=body,
                digestmod="sha256",
            ).hexdigest()
            return hmac.compare_digest(body_signature, signature)


# Import the config initialization from the original handler
from web_app_handler import init_config
