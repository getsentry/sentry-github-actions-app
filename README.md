# Github actions Sentry app

This app allows your organization to trace Github Actions with Sentry. You can use this to get insights of what parts of your CI are slow or failing often.
It works by listening to a Github workflow events via a webhook in your repository. These events are the stored in Sentry as performance transactions.

`github_sdk.py` has the generic logic to submit Github jobs as transactions. Eventually this file could be released separatedly.
`handle_event.py`: Business logic goes here.
`main.py` contains the code to respond to webhook events.

## Set up

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
  - `GH_SECRET`: Report errors to Sentry of the app itself
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
- Add a secret with `ruby -rsecurerandom -e 'puts SecureRandom.hex(20)'` on your command line
  - Set `GH_SECRET` as an env variable in your deployment
  - For more info, [read Github docs](https://docs.github.com/en/enterprise-server@3.4/developers/webhooks-and-events/webhooks/creating-webhooks)
- Enter the URL of the deployed app
  - Use an ngrok URL for local development (read next section)
- Save the webhook

**Note**: Webhook events will immediately be sent. Disable the hook if you're not ready.

## Local development

Prerequisites:

- [PDM](https://pdm.fming.dev/#installation) ([Helper script](https://gist.github.com/armenzg/4d2ac94bd770879d8df37c5da0fc7a33)) to manage Python requirements
- ngrok (for local dev)

You can ingest a single job without webhooks or starting the app by using the cli. For example:

```shell
# This is a normal URL of a job on Github
pdm run ingest https://github.com/getsentry/sentry/runs/5759197422?check_suite_focus=true
# From test fixture
pdm run ingest tests/fixtures/jobA/job.json
```

Steps to ingest events from a repository:

- Install ngrok, authenticate and start it up (`ngrok http 5001`)
  - Take note of the URL
- Create a Github webhook for the repo you want to analyze
  - Choose `workflow` events & make sure to choose `application/json`
  - Put Ngrok's URL there

Table of commands:

| Command           | Description                                        |
| ----------------- | -------------------------------------------------- |
| pdm run start     | Start the Flask app on <http://localhost:5001>     |
| pdm run bootstrap | Install pre-commit hooks                           |
| pdm run test      | Run Python tests                                   |
| pdm run coverage  | Get code coverage data and open results in browser |

## Sentry staff info

Google Cloud Build will automatically build a Docker image when the code merges on `master`. Logging to Google Cloud Run and deploy the latest image.
