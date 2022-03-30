from src.workflow_events import generate_transaction
from .fixtures import *


def test_workflow_without_steps(completed_workflow):
    completed_workflow["workflow_job"]["steps"] = []
    assert generate_transaction(completed_workflow["workflow_job"]) == None
