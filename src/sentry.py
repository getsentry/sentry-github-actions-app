import uuid

from sentry_sdk.envelope import Envelope
from sentry_sdk.utils import format_timestamp


def base_transaction():
    trace_id = uuid.uuid4().hex
    parent_span_id = uuid.uuid4().hex[16:]
    return {
        "event_id": uuid.uuid4().hex,
        "type": "transaction",
        "transaction": "default",
        "contexts": {
            "trace": {
                "trace_id": trace_id,
                "span_id": parent_span_id,
                "type": "trace",
            },
        },
    }
