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
    
    def __init__(self, token: str, dsn: str, dry_run: bool = False):
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
    
    def _get_workflow_run_data(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Get workflow run data, with caching"""
        run_id = job["run_id"]
        
        if run_id not in self.workflow_cache:
            # Extract data from job payload for webhook testing
            self.workflow_cache[run_id] = {
                "runs": {
                    "head_commit": {
                        "author": {"name": "GitHub Actions", "email": "actions@github.com"}
                    },
                    "head_branch": job.get("head_branch", "main"),
                    "head_sha": job.get("head_sha", "unknown"),
                    "run_attempt": job.get("run_attempt", 1),
                    "html_url": f"https://github.com/sergio-playground/sentry-gh-actions-test/actions/runs/{run_id}",
                    "repository": {"full_name": "sergio-playground/sentry-gh-actions-test"}
                },
                "workflow": {
                    "name": job.get("workflow_name", "Multi-Job Test"),
                    "path": ".github/workflows/multi-job-test.yml"
                },
                "repo": "sergio-playground/sentry-gh-actions-test"
            }
        
        return self.workflow_cache[run_id]
    
    def _create_workflow_transaction(self, job: Dict[str, Any], all_jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a single workflow transaction with job spans"""
        workflow_data = self._get_workflow_run_data(job)
        runs = workflow_data["runs"]
        workflow = workflow_data["workflow"]
        repo = workflow_data["repo"]
        
        # Calculate workflow start and end times
        job_start_times = [datetime.fromisoformat(j["started_at"].replace("Z", "+00:00")) for j in all_jobs if j.get("started_at")]
        job_end_times = [datetime.fromisoformat(j["completed_at"].replace("Z", "+00:00")) for j in all_jobs if j.get("completed_at")]
        
        workflow_start = min(job_start_times) if job_start_times else datetime.utcnow()
        workflow_end = max(job_end_times) if job_end_times else datetime.utcnow()
        
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
        
        # Create workflow transaction
        workflow_transaction = {
            "type": "transaction",
            "transaction": f"workflow: {workflow['name']}",  # Use "transaction" not "transaction_name"
            "platform": "python",
            "environment": "production",
            "release": runs.get("head_sha", "main")[:8],
            "sdk": {
                "name": "gha-sentry-workflow",
                "version": "0.0.1"
            },
            "contexts": {
                "trace": {
                    "span_id": get_uuid()[:16],
                    "trace_id": get_uuid_from_string(
                        f"workflow_run_id:{job['run_id']}_run_attempt:{job['run_attempt']}"
                    ),
                    "type": "trace",
                    "op": "workflow",
                    "description": f"GitHub Actions workflow: {workflow['name']}",
                    "status": workflow_status
                },
                "runtime": {
                    "name": "python",
                    "version": "3.8.0"
                }
            },
            "user": runs["head_commit"]["author"],
            "start_timestamp": workflow_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "timestamp": workflow_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": "info",
            "logger": "workflow_tracer",
            "tags": {
                "workflow_name": workflow["name"],
                "workflow_status": workflow_status,
                "branch": runs["head_branch"],
                "commit": runs["head_sha"],
                "repo": repo,
                "run_attempt": runs["run_attempt"],
                "total_jobs": len(all_jobs),
                "successful_jobs": len([j for j in all_jobs if j.get("conclusion") == "success"]),
                "failed_jobs": len([j for j in all_jobs if j.get("conclusion") == "failure"]),
                "cancelled_jobs": len([j for j in all_jobs if j.get("conclusion") == "cancelled"]),
                "skipped_jobs": len([j for j in all_jobs if j.get("conclusion") == "skipped"]),
                "trace_version": "v3.6"
            },
            "extra": {
                "workflow_url": runs["html_url"],
                "workflow_file": workflow["path"],
                "total_duration": (workflow_end - workflow_start).total_seconds()
            },
            "spans": []
        }
        
        # Add PR info if available
        if runs.get("pull_requests"):
            pr_number = runs["pull_requests"][0]["number"]
            workflow_transaction["extra"]["pr"] = f"https://github.com/{repo}/pull/{pr_number}"
            workflow_transaction["tags"]["pull_request"] = pr_number
        
        # Add job spans to the workflow transaction
        workflow_span_id = workflow_transaction["contexts"]["trace"]["span_id"]
        workflow_trace_id = workflow_transaction["contexts"]["trace"]["trace_id"]
        
        for job_data in all_jobs:
            # Create job span
            job_span = {
                "op": "job",
                "description": job_data["name"],
                "parent_span_id": workflow_span_id,
                "span_id": get_uuid()[:16],
                "start_timestamp": datetime.fromisoformat(job_data["started_at"].replace("Z", "+00:00")).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end_timestamp": datetime.fromisoformat(job_data["completed_at"].replace("Z", "+00:00")).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "trace_id": workflow_trace_id,
                "status": "ok" if job_data["conclusion"] in ["success", "skipped"] else "internal_error",
                "data": {
                    "job_url": job_data["html_url"],
                    "job_status": job_data["conclusion"],
                    "job_name": job_data["name"],
                    "job_id": job_data["id"]
                }
            }
            workflow_transaction["spans"].append(job_span)
            
            # Add step spans as children of job span
            for step in job_data.get("steps", []):
                step_span = {
                    "op": "step",
                    "description": step["name"],
                    "parent_span_id": job_span["span_id"],
                    "span_id": get_uuid()[:16],
                    "start_timestamp": datetime.fromisoformat(step["started_at"].replace("Z", "+00:00")).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end_timestamp": datetime.fromisoformat(step["completed_at"].replace("Z", "+00:00")).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "trace_id": workflow_trace_id,
                    "status": "ok" if step["conclusion"] == "success" else "internal_error",
                    "data": {
                        "step_name": step["name"],
                        "step_number": step["number"],
                        "step_conclusion": step["conclusion"]
                    }
                }
                workflow_transaction["spans"].append(step_span)
        
        return workflow_transaction
    
    
    def send_workflow_trace(self, job: Dict[str, Any], all_jobs: List[Dict[str, Any]] = None):
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
            workflow_transaction = self._create_workflow_transaction(job, all_jobs)
            workflow_trace_id = workflow_transaction["contexts"]["trace"]["trace_id"]
            
            # Log detailed transaction info
            logging.info(f"Workflow transaction details:")
            logging.info(f"  - Trace ID: {workflow_trace_id}")
            logging.info(f"  - Transaction name: {workflow_transaction['transaction']}")
            logging.info(f"  - Total spans: {len(workflow_transaction['spans'])}")
            logging.info(f"  - Trace version: {workflow_transaction['tags']['trace_version']}")
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
        import json
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
        
        # Create a copy of the transaction without event_id for sending to Sentry
        transaction_for_sentry = transaction.copy()
        if 'event_id' in transaction_for_sentry:
            del transaction_for_sentry['event_id']
        
        envelope = Envelope()
        envelope.add_transaction(transaction_for_sentry)
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
        
        req = requests.post(
            self.sentry_project_url,
            data=body.getvalue(),
            headers=headers,
        )
        
        logging.info(f"Sentry response: {req.status_code} - {req.text}")
        req.raise_for_status()
        return req
