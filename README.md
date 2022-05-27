# Github actions Sentry app

**DISCLAIMER**: This app/sdk are still in experimental mode. Please file an issue and ask of the current state before going ahead and using it.

This app allows your organization to trace Github Actions with Sentry. You can use this to get insights of what parts of your CI are slow or failing often.
It works by listening to a Github workflow events via a webhook in your repository. These events are the stored in Sentry as performance transactions.

`github_sdk.py` has the generic logic to submit Github jobs as transactions. Eventually this file could be released separatedly.
`event_handler.py`: Business logic goes here.
`main.py` contains the code to respond to webhook events.

You can set up this app following the instructions under "Self-hosted". We also have a Github app to increase the security, however, it can only be installed in the `getsentry` Github org. In the future, we may make it pubclicly available. There's few things we need to figure out before we do.

## Github app

Currently, it is only used internally. We do not have a way of mapping CI events from one org to a specific Sentry dsn.

### Current configuration

- The App's webhook will point to the official deployment and share the same secret
- Grant XYZ permissions

## Self-hosted

### Sentry

In Sentry.io (or self-hosted install):

- Create a project to track errors of the app itself (`APP_DSN` in section below)
- Create a project to track Github jobs (`SENTRY_GITHUB_DSN` in section below)

### Create a Github personal token

- Create a [personal token](https://github.com/settings/tokens)
  - You do not need to give it any scopes
  - Take note of the token as you will need to define it as `GH_TOKEN` in the next section
  - After creating the token, some orgs [require authorizing tokens](https://docs.github.com/en/enterprise-cloud@latest/authentication/authenticating-with-saml-single-sign-on/authorizing-a-personal-access-token-for-use-with-saml-single-sign-on), thus, select "Configure SSO" if you see it
- If this is for development, you can place the token in a file named `.env` as `GH_TOKEN`

### Deployment set up

- Deploy the app to a service (e.g. GCP) and make it publicly reachable
- Take note of the app's URL and use it when creating the Github webhook
- Environment variables:
  - `APP_DSN`: Report errors to Sentry of the app itself
  - `GH_WEBHOOK_SECRET`: Secret shared between Github's webhook and your app
  - `GH_TOKEN`: This is used to validate API calls are coming from Github webhook
  - `SENTRY_GITHUB_DSN`: Where to report Github job transactions
  - `LOGGING_LEVEL` (optional): To set the verbosity of Python's logging (defaults to INFO)

**Optional**: Once you have a deployment, you may wish to go back to Sentry and whitelist the deployment.

### Github webhook

Create a Github webhook for a repo (or an org):

- Under settings select "Webhooks":
- Choose "Add webhook"
- Choose `application/json`
- Choose `workflow` events
- Add a secret with `python3 -c 'import secrets; print(secrets.token_urlsafe(20))'` on your command line
  - Set `GH_WEBHOOK_SECRET` as an env variable in your deployment
  - For more info, [read Github docs](https://docs.github.com/en/enterprise-server@3.4/developers/webhooks-and-events/webhooks/creating-webhooks)
- Enter the URL of the deployed app
  - Use an ngrok URL for local development (read next section)
- Save the webhook

**Note**: Webhook events will immediately be sent. Disable the hook if you're not ready.

## Local development

Prerequisites:

- ngrok (for local dev)

Set up:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install wheel
pip install -r requirements.txt -r requirements-dev.txt
```

You can ingest a single job without webhooks or starting the app by using the cli. For example:

```shell
# This is a normal URL of a job on Github
python3 cli.py https://github.com/getsentry/sentry/runs/5759197422?check_suite_focus=true
# From test fixture
python3 cli.py tests/fixtures/jobA/job.json
```

Steps to ingest events from a repository:

- Install ngrok, authenticate and start it up (`ngrok http 5001`)
  - Take note of the URL
- Create a Github webhook for the repo you want to analyze
  - Choose `Workflow jobs` events & make sure to choose `application/json`
  - Put Ngrok's URL there

Table of commands:

| Command                            | Description                                    |
| ---------------------------------- | ---------------------------------------------- |
| flask run -p 5001                  | Start the Flask app on <http://localhost:5001> |
| pre-commit install                 | Install pre-commit hooks                       |
| pytest                             | Run Python tests                               |
| pytest --cov=src --cov-report=html | Generate code coverage.                        |

If you want to test the Github App set up, you need to make the App's webhook point to your ngrok set up, define `GH_APP_ID` and `GH_APP_PRIVATE_KEY_PATH` as env variables.

## Sentry staff info

Google Cloud Build will automatically build a Docker image when the code merges on `main`. Logging to Google Cloud Run and deploy the latest image.
