from src.trace import send_trace
from .fixtures import *


def test_workflow_without_steps(skipped_workflow):
    assert send_trace(skipped_workflow) == None
