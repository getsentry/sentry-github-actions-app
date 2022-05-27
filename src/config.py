import logging
import os

from google.cloud import secretmanager

LOGGING_LEVEL = os.environ.get("LOGGING_LEVEL", logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)

client = secretmanager.SecretManagerServiceClient()


def fetch_secret(secret: str, version: int) -> str:
    uri = f"projects/sentry-dev-tooling/secrets/{secret}/versions/{version}"
    logger.info(f"Grabbing secret from {uri}")
    return client.access_secret_version(name=uri).payload.data.decode("UTF-8")


def init():
    """
    Return configuration dict based on environment variables
    """
    config = {}
    # This variable is the key to enabling Github App mode or not
    # XXX: Document in README.md where to obtain installation ID
    if os.environ.get("GH_APP_ID"):
        config["gh_app"] = {
            "app_id": os.environ["GH_APP_ID"],
            "installation_id": os.environ["GH_INSTALLATIN_ID"],
        }

    # K_SERVICE is a reserved variable for Google Cloud services
    if os.environ.get("K_SERVICE"):
        config["gh_app"]["private_key"] = fetch_secret("GithubAppPrivateKey", 1)
    else:
        # This block only applies for development since we are not executing on GCP
        if os.environ.get("GH_APP_ID"):
            with open(os.environ["GH_APP_PRIVATE_KEY_PATH"], "rb") as f:
                config["gh_app"]["private_key"] = f.read()

    return config
