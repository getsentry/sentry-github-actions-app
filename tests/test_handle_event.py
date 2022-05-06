from src.handle_event import handle_event


def test_invalid_request():
    reason, http_code = handle_event(data={}, headers={})
    assert reason == "Event not supported."
    assert http_code == 200


def test_bad_data():
    reason, http_code = handle_event(
        data={
            "action": "invalid_value",
        },
        headers={
            "X-GitHub-Event": "workflow_job",
        },
    )
    assert reason == "We cannot do anything with this workflow state."
    assert http_code == 200


# XXX: Need to patch here
def test_calls_send_trace():
    pass


# XXX: Write tests that raise exceptions
