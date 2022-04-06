from src.trace import generate_trace
from .fixtures import *


def test_workflow_without_steps(skipped_workflow):
    assert generate_trace(skipped_workflow) == None
