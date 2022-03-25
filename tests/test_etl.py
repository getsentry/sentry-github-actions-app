from src.workflow_events import generate_transaction
from .fixtures import *

# XXX: How do we test when timestamps and uuids change? freezegun?
# XXX: We also need to prevent requests from happening
@pytest.mark.skip("This test is not yet useful")
def test_generate_transaction(completed_workflow, generated_transaction):
    assert generate_transaction(completed_workflow["workflow_job"]) == (
        generated_transaction
    )


def test_workflow_without_steps(completed_workflow):
    completed_workflow["workflow_job"]["steps"] = []
    assert generate_transaction(completed_workflow["workflow_job"]) == None
