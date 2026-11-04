from __future__ import annotations

import logging
import os
from typing import Any
from typing import NoReturn

import sentry_sdk
from flask import abort
from flask import Flask
from flask import jsonify
from flask import request
from flask import Response
from sentry_sdk import capture_exception
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.scrubber import EventScrubber

from .web_app_handler import WebAppHandler


def init_sentry(dsn: str, **options: Any) -> None:
    # This tracks errors and performance of the app itself rather than GH workflows
    sentry_sdk.init(
        dsn=dsn,
        integrations=[FlaskIntegration()],
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=1.0,
        environment=os.environ.get("FLASK_ENV", "production"),
        # GitHub tokens sit in dicts in the frames' local variables (e.g. the request
        # `headers` and the access token response), and the default scrubber only
        # checks top-level variable names
        event_scrubber=EventScrubber(recursive=True),
        **options,
    )


APP_DSN = os.environ.get("APP_DSN")
if APP_DSN:
    init_sentry(APP_DSN)

LOGGING_LEVEL = os.environ.get("LOGGING_LEVEL", "INFO")
# Set the logging level for all loggers (e.g. requests)
logging.getLogger().setLevel(LOGGING_LEVEL)
logging.basicConfig()

# Logger for this module
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)
logger.info("App logging is working.")

handler = WebAppHandler()

app = Flask(__name__)


@app.route("/", methods=["POST"])
def main() -> tuple[Response, int]:
    if not handler.valid_signature(request.data, request.headers):
        abort(
            400,
            "The secret you are using on your Github webhook does not match this app's secret.",
        )

    # Top-level crash preventing try block
    try:
        reason, http_code = handler.handle_event(request.json, request.headers)
        return jsonify({"reason": reason}), http_code
    except Exception as e:
        logger.exception(e)
        capture_exception(e)
        return jsonify({"reason": "There was an error."}), 500


if os.environ.get("FLASK_ENV") == "development":

    @app.route("/debug-sentry")
    def trigger_error() -> NoReturn:
        try:
            raise ZeroDivisionError("division by zero")
        except Exception as e:
            # Report it to Sentry
            capture_exception(e)
            # Let Flask handle the rest
            raise e
