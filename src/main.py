import logging
import os

import sentry_sdk
from flask import jsonify, request, Flask

from .handle_event import handle_event

APP_DSN = os.environ.get("APP_DSN")
if APP_DSN:
    # This tracks errors and performance of the app itself rather than GH workflows
    sentry_sdk.init(
        dsn=APP_DSN,
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


@app.route("/", methods=["POST"])
def main():
    payload = {"reason": "There was an error."}
    http_code = 500
    # Top-level crash preventing try block
    try:
        reason, http_code = handle_event(request.json, request.headers)
        payload = {"reason": reason}
    finally:
        return jsonify(payload), http_code
