from unittest import mock

from src.trace import _base_transaction, send_trace
from .fixtures import *


# XXX: In _base_transaction we call it 3 times, thus, it should really be returning
# three different values
class UUID:
    hex = "06a005dd99324b5e8b7f874be7d41568"


@mock.patch("src.trace.uuid.uuid4")
def test_base_transaction(mock_uuid):
    mock_uuid.return_value = UUID

    assert _base_transaction() == {
        "contexts": {
            "trace": {
                "span_id": UUID.hex[16:],
                "trace_id": UUID.hex,
                "type": "trace",
            }
        },
        "event_id": UUID.hex,
        "transaction": "default",
        "type": "transaction",
        "user": {},
    }


def test_workflow_without_steps(skipped_workflow):
    assert send_trace(skipped_workflow) == None
