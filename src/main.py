import logging
import os

import sentry_sdk
from flask import abort, jsonify, request, Flask
from sentry_sdk import capture_exception

from sentry_sdk.integrations.flask import FlaskIntegration

from .github_app import get_access_tokens
from .event_handler import EventHandler

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


# The app can run in one mode or the other
if os.environ.get("GH_APP_ID"):
    access_tokens = get_access_tokens()
    # XXX: We will change this in following PRs
    TOKEN = access_tokens["armenzg-dev"]
elif os.environ["GH_TOKEN"]:
    # We need an authorized token to fetch the API. If you have SSO on your org
    # you will need to grant permission.
    # You can create an .env file and place the token in it
    TOKEN = os.environ["GH_TOKEN"]

# Where to report Github actions transactions
SENTRY_GITHUB_DSN = os.environ.get("SENTRY_GITHUB_DSN")

app = Flask(__name__)
handler = EventHandler(
    secret=os.environ.get("GH_WEBHOOK_SECRET"),
    token=TOKEN,
    dsn=SENTRY_GITHUB_DSN,
)


@app.route("/", methods=["POST"])
def main():
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
    def trigger_error():
        try:
            1 / 0
        except Exception as e:
            # Report it to Sentry
            capture_exception(e)
            # Let Flask handle the rest
            raise e
