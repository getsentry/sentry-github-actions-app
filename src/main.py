import logging
import os

import sentry_sdk
from flask import jsonify, request, Flask
from sentry_sdk.integrations.flask import FlaskIntegration

from .github_sdk import send_trace

APP_DSN = os.environ.get("APP_DSN")
if APP_DSN:
    # This tracks errors and performance of the app itself rather than GH workflows
    sentry_sdk.init(
        dsn=APP_DSN,
        integrations=[FlaskIntegration()],
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=1.0,
        environment=os.environ.get("FLASK_ENV", "production"),
    )

LOGGING_LEVEL = os.environ.get("LOGGING_LEVEL", "INFO")
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)

app = Flask(__name__)


def handle_event(data, headers):
    if headers.get("X-GitHub-Event") != "workflow_job":
        # We return 200 to make webhook not turn red
        return {"reason": "Event not supported."}, 200

    if data["action"] != "completed":
        return ({"reason": "We cannot do anything with this workflow state."}, 200)

    send_trace(data["workflow_job"])
    return {"reason": "OK"}, 200


@app.route("/", methods=["POST"])
def main():
    payload = {"reason": "There was an error."}
    http_code = 500
    # Top-level crash preventing try block
    try:
        payload, http_code = handle_event(request.json, request.headers)
    finally:
        return jsonify(payload), http_code
