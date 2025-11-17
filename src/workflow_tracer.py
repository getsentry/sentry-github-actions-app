"""
Enhanced workflow tracing that creates a parent workflow transaction
to encapsulate all jobs and provide total workflow duration
"""

import json
import logging
import uuid
import hashlib
from datetime import datetime
from typing import Dict, List, Any, Optional
import requests
try:
    from sentry_sdk.envelope import Envelope
    from sentry_sdk.utils import format_timestamp
except ImportError:
    # Fallback for testing
    class Envelope:
        def add_transaction(self, transaction): pass
        def serialize_into(self, f): pass
    
    def format_timestamp(dt):
        return dt.isoformat() + "Z"


def get_uuid():
    return uuid.uuid4().hex


def get_uuid_from_string(input_string):
    hash_object = hashlib.sha256(input_string.encode())
    hash_value = hash_object.hexdigest()
    return uuid.UUID(hash_value[:32]).hex


class WorkflowTracer:
    """Enhanced tracer that creates workflow-level transactions"""
    
    def __init__(self, token: Optional[str], dsn: str, dry_run: bool = False):
        self.token = token
        self.dsn = dsn
        self.dry_run = dry_run
        self.workflow_cache = {}  # Cache workflow runs to avoid duplicate API calls
        
        if dsn:
            # Parse DSN: https://key@host/project_id
            dsn_parts = dsn.split("@")
            if len(dsn_parts) != 2:
                raise ValueError(f"Invalid DSN format: {dsn}")
            
            sentry_key = dsn_parts[0].split("//")[1]
            host_and_project = dsn_parts[1]
            
            # Split host and project_id
            host_parts = host_and_project.split("/")
            if len(host_parts) != 2:
                raise ValueError(f"Invalid DSN format: {dsn}")
            
            host = host_parts[0]
            project_id = host_parts[1]
            
            self.sentry_key = sentry_key
            self.sentry_project_url = f"https://{host}/api/{project_id}/envelope/"
    
    def _fetch_github(self, url: str) -> requests.Response:
        """Fetch data from GitHub API"""
        headers = {"Authorization": f"token {self.token}"}
        req = requests.get(url, headers=headers)
        req.raise_for_status()
        return req
    
    def _get_workflow_run_data(self, job: Dict[str, Any], repository_info: Dict[str, Any] = None) -> Dict[str, Any]:
        """Get workflow run data, with caching"""
        run_id = job["run_id"]
        
        if run_id not in self.workflow_cache:
            # Extract repository info from webhook payload or use defaults
            repo_full_name = "unknown/unknown"
            if repository_info:
                repo_full_name = repository_info.get("full_name", repo_full_name)
            elif "repository" in job:
                repo_full_name = job["repository"].get("full_name", repo_full_name)
            
            # Extract workflow info from job or use defaults
            workflow_name = job.get("workflow_name") or job.get("name", "Unknown Workflow")
            workflow_path = job.get("workflow_path", ".github/workflows/workflow.yml")
            
            # Extract commit author info if available
            author_name = "GitHub Actions"
            author_email = "actions@github.com"
            if "head_commit" in job and "author" in job.get("head_commit", {}):
                author_name = job["head_commit"]["author"].get("name", author_name)
                author_email = job["head_commit"]["author"].get("email", author_email)
            
            # Fetch workflow run details from GitHub API to get created_at and updated_at
            workflow_run_created_at = None
            workflow_run_updated_at = None
            if self.token and repo_full_name != "unknown/unknown":
                try:
                    # GitHub API endpoint: GET /repos/{owner}/{repo}/actions/runs/{run_id}
                    api_url = f"https://api.github.com/repos/{repo_full_name}/actions/runs/{run_id}"
                    headers = {"Authorization": f"token {self.token}"}
                    
                    logging.debug(f"Fetching workflow run details for run {run_id} from GitHub API")
                    response = self._fetch_github(api_url)
                    run_data = response.json()
                    
                    workflow_run_created_at = run_data.get("created_at")
                    workflow_run_updated_at = run_data.get("updated_at")
                    
                    if workflow_run_created_at and workflow_run_updated_at:
                        logging.debug(
                            f"Fetched workflow run timestamps: created_at={workflow_run_created_at}, "
                            f"updated_at={workflow_run_updated_at}"
                        )
                    else:
                        logging.warning(
                            f"Workflow run API response missing timestamps for run {run_id}, "
                            "will fall back to job timestamps"
                        )
                except Exception as e:
                    logging.warning(
                        f"Failed to fetch workflow run details for run {run_id}: {e}. "
                        "Will fall back to job timestamps."
                    )
            
            self.workflow_cache[run_id] = {
                "runs": {
                    "head_commit": {
                        "author": {"name": author_name, "email": author_email}
                    },
                    "head_branch": job.get("head_branch", "main"),
                    "head_sha": job.get("head_sha", "unknown"),
                    "run_attempt": job.get("run_attempt", 1),
                    "html_url": f"https://github.com/{repo_full_name}/actions/runs/{run_id}",
                    "repository": {"full_name": repo_full_name},
                    "created_at": workflow_run_created_at,
                    "updated_at": workflow_run_updated_at
                },
                "workflow": {
                    "name": workflow_name,
                    "path": workflow_path
                },
                "repo": repo_full_name
            }
        
        return self.workflow_cache[run_id]
    
    def _create_workflow_transaction(self, job: Dict[str, Any], all_jobs: List[Dict[str, Any]], repository_info: Dict[str, Any] = None) -> Dict[str, Any]:
        """Create a single workflow transaction with job spans"""
        workflow_data = self._get_workflow_run_data(job, repository_info)
        runs = workflow_data["runs"]
        workflow = workflow_data["workflow"]
        repo = workflow_data["repo"]
        
        # Determine overall workflow status
        job_conclusions = [j.get("conclusion") for j in all_jobs]
        if "failure" in job_conclusions:
            workflow_status = "internal_error"
        elif "cancelled" in job_conclusions:
            workflow_status = "cancelled"
        elif "skipped" in job_conclusions:
            workflow_status = "skipped"
        else:
            workflow_status = "ok"
        
        # Prepare data and tags similar to github_sdk.py structure
        workflow_data_dict = {
            "workflow_url": runs["html_url"],
        }
        workflow_tags = {
            "branch": runs["head_branch"],
            "commit": runs["head_sha"],
            "repo": repo,
            "run_attempt": runs["run_attempt"],
            "workflow": workflow["path"].rsplit("/")[-1],
        }
        
        # Add PR info if available
        if runs.get("pull_requests"):
            pr_number = runs["pull_requests"][0]["number"]
            workflow_data_dict["pr"] = f"https://github.com/{repo}/pull/{pr_number}"
            workflow_tags["pull_request"] = pr_number
        
        # Re-fetch workflow run data to get the final updated_at timestamp
        # This ensures we have the most up-to-date completion time
        workflow_run_created_at = runs.get("created_at")
        workflow_run_updated_at = runs.get("updated_at")
        
        # Re-fetch workflow run details right before sending to get final updated_at
        repo_full_name = repo
        if self.token and repo_full_name != "unknown/unknown" and job.get("run_id"):
            try:
                run_id = job["run_id"]
                api_url = f"https://api.github.com/repos/{repo_full_name}/actions/runs/{run_id}"
                logging.debug(f"Re-fetching workflow run details for run {run_id} to get final updated_at")
                response = self._fetch_github(api_url)
                run_data = response.json()
                
                # Update with the latest timestamps
                workflow_run_created_at = run_data.get("created_at")
                workflow_run_updated_at = run_data.get("updated_at")
                
                # Update cache with latest data
                if run_id in self.workflow_cache:
                    self.workflow_cache[run_id]["runs"]["created_at"] = workflow_run_created_at
                    self.workflow_cache[run_id]["runs"]["updated_at"] = workflow_run_updated_at
                
                logging.debug(
                    f"Re-fetched workflow run timestamps: created_at={workflow_run_created_at}, "
                    f"updated_at={workflow_run_updated_at}"
                )
            except Exception as e:
                logging.warning(
                    f"Failed to re-fetch workflow run details for run {job.get('run_id')}: {e}. "
                    "Using cached timestamps."
                )
        
        # Calculate workflow timestamps - prefer workflow run created_at/updated_at to match GitHub's duration
        # Fall back to job timestamps if workflow run timestamps are not available
        if workflow_run_created_at and workflow_run_updated_at:
            # Use workflow run timestamps (matches GitHub's duration calculation)
            workflow_start_str = workflow_run_created_at
            workflow_end_str = workflow_run_updated_at
            logging.debug(
                f"Using workflow run timestamps: {workflow_start_str} -> {workflow_end_str} "
                f"(matches GitHub's duration calculation)"
            )
        else:
            # Fall back to job timestamps (earliest job start to latest job end)
            workflow_start_str = min([j["started_at"] for j in all_jobs if j.get("started_at")], default=all_jobs[0]["started_at"])
            workflow_end_str = max([j["completed_at"] for j in all_jobs if j.get("completed_at")], default=all_jobs[0]["completed_at"])
            logging.debug(
                f"Using job timestamps (fallback): {workflow_start_str} -> {workflow_end_str}"
            )
        
        # Create workflow transaction matching github_sdk.py structure
        workflow_transaction = {
            "event_id": get_uuid(),
            "type": "transaction",
            "transaction": f"workflow: {workflow['name']}",
            "contexts": {
                "trace": {
                    "span_id": get_uuid()[:16],
                    "trace_id": get_uuid_from_string(
                        f"workflow_run_id:{job['run_id']}_run_attempt:{job['run_attempt']}"
                    ),
                    "type": "trace",
                    "op": f"workflow: {workflow['name']}",
                    "description": f"workflow: {workflow['name']}",
                    "status": workflow_status,
                    "data": workflow_data_dict
                }
            },
            "user": runs["head_commit"]["author"],
            "start_timestamp": workflow_start_str,
            "timestamp": workflow_end_str,
            "tags": workflow_tags,
            "spans": []
        }
        
        # Calculate cleanup/teardown time (delta between last job completion and workflow updated_at)
        cleanup_duration_seconds = 0
        if workflow_run_created_at and workflow_run_updated_at:
            # Find the latest job completion time
            latest_job_completion = max([j["completed_at"] for j in all_jobs if j.get("completed_at")], default=None)
            if latest_job_completion:
                try:
                    from datetime import datetime
                    latest_job_dt = datetime.fromisoformat(latest_job_completion.replace("Z", "+00:00"))
                    workflow_end_dt = datetime.fromisoformat(workflow_run_updated_at.replace("Z", "+00:00"))
                    cleanup_duration_seconds = (workflow_end_dt - latest_job_dt).total_seconds()
                    
                    if cleanup_duration_seconds > 0:
                        logging.debug(
                            f"Cleanup/teardown time: {cleanup_duration_seconds:.1f}s "
                            f"(between last job completion and workflow completion)"
                        )
                except Exception as e:
                    logging.warning(f"Failed to calculate cleanup duration: {e}")
        
        # Add job spans to the workflow transaction
        workflow_span_id = workflow_transaction["contexts"]["trace"]["span_id"]
        workflow_trace_id = workflow_transaction["contexts"]["trace"]["trace_id"]
        
        for job_data in all_jobs:
            # Create job span matching github_sdk.py format
            job_span = {
                "op": job_data["name"],
                "name": job_data["name"],
                "parent_span_id": workflow_span_id,
                "span_id": get_uuid()[:16],
                "start_timestamp": job_data["started_at"],
                "timestamp": job_data["completed_at"],
                "trace_id": workflow_trace_id,
            }
            workflow_transaction["spans"].append(job_span)
            
            # Add step spans as children of job span, matching github_sdk.py format
            for step in job_data.get("steps", []):
                try:
                    step_span = {
                        "op": step["name"],
                        "name": step["name"],
                        "parent_span_id": job_span["span_id"],
                        "span_id": get_uuid()[:16],
                        "start_timestamp": step["started_at"],
                        "timestamp": step["completed_at"],
                        "trace_id": workflow_trace_id,
                    }
                    workflow_transaction["spans"].append(step_span)
                except Exception as e:
                    logging.exception(e)
        
        # Add cleanup/teardown span if there's a delta between last job and workflow completion
        if cleanup_duration_seconds > 0:
            # Find the latest job completion timestamp to start cleanup span from
            latest_job_completion = max([j["completed_at"] for j in all_jobs if j.get("completed_at")], default=None)
            if latest_job_completion:
                try:
                    from datetime import datetime, timedelta
                    cleanup_start_dt = datetime.fromisoformat(latest_job_completion.replace("Z", "+00:00"))
                    cleanup_end_dt = cleanup_start_dt + timedelta(seconds=cleanup_duration_seconds)
                    
                    cleanup_span = {
                        "op": "workflow.cleanup",
                        "name": "Workflow cleanup and teardown",
                        "parent_span_id": workflow_span_id,
                        "span_id": get_uuid()[:16],
                        "start_timestamp": cleanup_start_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                        "timestamp": cleanup_end_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                        "trace_id": workflow_trace_id,
                    }
                    workflow_transaction["spans"].append(cleanup_span)
                    logging.debug(
                        f"Added cleanup span: {cleanup_duration_seconds:.1f}s "
                        f"({cleanup_start_dt.strftime('%H:%M:%S')} -> {cleanup_end_dt.strftime('%H:%M:%S')})"
                    )
                except Exception as e:
                    logging.warning(f"Failed to create cleanup span: {e}")
        
        return workflow_transaction
    
    
    def send_workflow_trace(self, job: Dict[str, Any], all_jobs: List[Dict[str, Any]] = None, repository_info: Dict[str, Any] = None):
        """Send a single workflow transaction with all job and step spans"""
        if self.dry_run:
            logging.info(f"Dry run: Would send workflow trace for {job['name']}")
            return
        
        if all_jobs is None:
            all_jobs = [job]
        
        try:
            logging.info(f"Creating workflow transaction for {len(all_jobs)} jobs")
            logging.info(f"Job names: {[j['name'] for j in all_jobs]}")
            
            # Create single workflow transaction with all spans
            workflow_transaction = self._create_workflow_transaction(job, all_jobs, repository_info)
            workflow_trace_id = workflow_transaction["contexts"]["trace"]["trace_id"]
            
            # Log detailed transaction info
            logging.info(f"Workflow transaction details:")
            logging.info(f"  - Trace ID: {workflow_trace_id}")
            logging.info(f"  - Transaction name: {workflow_transaction['transaction']}")
            logging.info(f"  - Total spans: {len(workflow_transaction['spans'])}")
            logging.info(f"  - Trace version: {workflow_transaction.get('tags', {}).get('trace_version', 'N/A')}")
            logging.info(f"  - Workflow status: {workflow_transaction['contexts']['trace']['status']}")
            
            # Log span details
            job_spans = [s for s in workflow_transaction['spans'] if s['op'] == 'job']
            step_spans = [s for s in workflow_transaction['spans'] if s['op'] == 'step']
            logging.info(f"  - Job spans: {len(job_spans)}")
            logging.info(f"  - Step spans: {len(step_spans)}")
            
            logging.info(f"Sending workflow transaction with trace_id: {workflow_trace_id}")
            # Send single workflow transaction
            self._send_envelope(workflow_transaction)
                
            logging.info(f"Successfully sent workflow trace with {len(all_jobs)} jobs")
            
        except Exception as e:
            logging.error(f"Error in send_workflow_trace: {e}", exc_info=True)
            raise
    
    def _send_envelope(self, transaction: Dict[str, Any]):
        """Send transaction to Sentry"""
        if self.dry_run:
            return
        
        # Save transaction payload for Postman testing
        trace_id = transaction.get('contexts', {}).get('trace', {}).get('trace_id', 'unknown')
        filename = f"transaction_payload_{trace_id}.json"
        
        with open(filename, 'w') as f:
            json.dump(transaction, f, indent=2)
        
        logging.info(f"💾 Transaction payload saved to: {filename}")
        logging.info(f"📋 Transaction details:")
        logging.info(f"  - Trace ID: {trace_id}")
        logging.info(f"  - Transaction: {transaction.get('transaction')}")
        logging.info(f"  - Total spans: {len(transaction.get('spans', []))}")
        logging.info(f"  - Trace version: {transaction.get('tags', {}).get('trace_version')}")
        
        logging.info(f"Sending envelope to Sentry: {self.sentry_project_url}")
        logging.info(f"Transaction type: {transaction.get('type')}")
        logging.info(f"Transaction name: {transaction.get('transaction')}")
        logging.info(f"Trace ID: {transaction.get('contexts', {}).get('trace', {}).get('trace_id')}")
        logging.info(f"Event ID: {transaction.get('event_id')}")
        
        # Send transaction as-is (event_id is included, matching github_sdk.py)
        envelope = Envelope()
        envelope.add_transaction(transaction)
        now = datetime.utcnow()
        
        headers = {
            "event_id": get_uuid(),
            "sent_at": format_timestamp(now),
            "Content-Type": "application/x-sentry-envelope",
            "Content-Encoding": "gzip",
            "X-Sentry-Auth": f"Sentry sentry_key={self.sentry_key},"
                            + f"sentry_client=gha-sentry-workflow/0.0.1,sentry_timestamp={now},"
                            + "sentry_version=7",
        }
        
        import io
        import gzip
        
        body = io.BytesIO()
        with gzip.GzipFile(fileobj=body, mode="w") as f:
            envelope.serialize_into(f)
        
        logging.info(f"Envelope size: {len(body.getvalue())} bytes")
        
        try:
            req = requests.post(
                self.sentry_project_url,
                data=body.getvalue(),
                headers=headers,
            )
            
            logging.info(f"✅ Sentry response: {req.status_code}")
            if req.status_code != 200:
                logging.error(f"❌ Sentry rejected transaction: {req.status_code} - {req.text[:500]}")
            else:
                logging.info(f"✅ Transaction successfully sent to Sentry")
            
            req.raise_for_status()
            return req
        except requests.exceptions.RequestException as e:
            logging.error(f"❌ Failed to send transaction to Sentry: {e}")
            logging.error(f"   URL: {self.sentry_project_url}")
            logging.error(f"   Trace ID: {trace_id}")
            raise
