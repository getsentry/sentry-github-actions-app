# Sentry Github Actions App

**NOTE**: If this is a project you would like us to invest in, please let us know in [this issue](https://github.com/getsentry/sentry-github-actions-app/issues/46).

This app allows your organization to instrument Github Actions with Sentry. You can use this to get insights of what parts of your CI are slow or failing often.

It works by listening to Github workflow events via a webhook configured in a Github App. These events are then stored in Sentry as performance transactions. The best value for this project is when you have [Sentry's Discover](https://docs.sentry.io/product/discover-queries/) and [Dashboards](https://docs.sentry.io/product/dashboards/) in order to slice the data and answer the questions you care about. In a sense, this project turns Github's CI as an app that Sentry monitors, thus, you can use many of the features you're familiar with.

There's likely products out there that can give you insights into Github's CI, however, this may be cheaper, it saves you having to add another vendor and your developers are already familiar with using Sentry.

## Examples

This screenshot shows that you can group Github Actions through various tags in Sentry's Discover:

<img width="711" alt="image" src="https://user-images.githubusercontent.com/44410/175557087-2ca904e1-d815-4ae0-a6a1-01b4ca38323a.png">

This screenshot shows the transaction view for an individual Github Action showing each step of the job:

<img width="992" alt="image" src="https://user-images.githubusercontent.com/44410/175558737-7eca4036-73ce-4ed2-8b5a-51b5d882a814.png">


## Features

Here's a list of benefits you will get if you use this project:

- Visualize a Github job and the breakdown per step
- Create CI alerts
  - For instance, if your main branch has a failure rate above a certain threshold
- Create widgets and dashboards showing your CI data
  - For instance, slowest jobs, most failing jobs, jobs requirying re-runs, repos consuming most CI
  - Some of the main tags by which you can slice the data: workflow file, repo, branch, commit, job_status, pull_request, run_attempt


## Do you want to try this?

Steps to follow:

- Fork the app
- Create a Docker build
- Deploy the image to your provider
  - If you don't use GCP you may need to make some changes to the code
- Create a Github App and install it in all your repos
  - Instructions are provided below

Please, give us some feedback in [this issue](https://github.com/getsentry/sentry-github-actions-app/issues/46).

## Code

Code explanation:

- `github_sdk.py` has the generic logic to submit Github jobs as Sentry transactions. This module could be released separatedly.
- `github_app.py` contains code to handle a Github App installation.
- `web_app_handler.py`: Web app logic goes here.
- `main.py` contains the code to respond to webhook events.

## Set Up

**NOTE**: Currently, this app is only used internally. See [milestone](https://github.com/getsentry/sentry-github-actions-app/milestone/1) for required work to support ingesting data from other orgs.

These are the steps you will need to set this backend and Github app for your organization.

The steps of the next two sections are related. You will be generating keys and variables that are need to configure each component (the backend and the Github App), thus, you will need to go back and forth.

### Sentry SaaS (or self-hosted Sentry)

In Sentry.io:

- Create a project to track errors of the backend itself (`APP_DSN` in section below)
- Create a project to track Github jobs (`SENTRY_GITHUB_DSN` in section below)

### Backend deployment

- Deploy the app to a service (e.g. GCP) and make it publicly reachable
  - Take note of the app's URL and use it when creating the Github app webhook

Common environment variables:

- `APP_DSN`: Report your deployment errors to Sentry
- `GH_WEBHOOK_SECRET`: Secret shared between Github's webhook and your app
  - Create a secret with `python3 -c 'import secrets; print(secrets.token_urlsafe(20))'` on your command line
- `SENTRY_GITHUB_DSN`: Where to report your Github job transactions
- `LOGGING_LEVEL` (optional): To set the verbosity of Python's logging (defaults to INFO)

Github App specific variables:

- `GH_APP_ID` - Github App ID
  - When you create the Github App, you will see the value listed in the page
- `GH_APP_INSTALLATION_ID` - Github App Installation ID
  - Once you install the app under your Github org, you will see it listed as one of your organizations' integrations
  - If you load the page, you will see the ID as part of the URL
- `GH_APP_PRIVATE_KEY` - Private key
  - When you load the Github App page, at the bottom of the page under "Private Keys" select "Generate a private key"
  - A .pem file will be downloaded locally.
  - Convert it into a single line value by using base64 (`base64 -i path_to_pem_file`)

For local development, you need to make the App's webhook point to your ngrok set up. You should create a new private key (a .pem file that gets automatically downloaded when generated) for your local development and do not forget to delete the private key when you are done.

### The Github App

After creating the Github App for the first time there are some changes you need to make:

- Configure the Webhook URL to point to the backend deployment
- Set the Webhook Secret to be the same as the backend deployment
- Set the following permissions for the app:
  - Actions: Workflows, workflow runs and artifacts -> Read-only
   - Specific events: [Workflow job](https://docs.github.com/en/developers/webhooks-and-events/webhooks/webhook-events-and-payloads#workflow_job)

After completing the creation of the app you will need to make few more changes:

- Click on `Generate a private key`
  - Run `base64 -i <path_to_download_file>`
  - Store the value in Google Secrets
  - Delete the file just downloaded
- Add to the deployment the variable `GH_APP_ID`
- Select "Install App" and install the app on your Github org
  - Grant access to "All Repositories"
- Look at the URL of the installation and you will find the installation ID
  - Add to the deployment the variable `GH_APP_INSTALLATION_ID`

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

You can ingest a single job without webhooks by using the cli. For example:

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

## Sentry staff info

Google Cloud Build will automatically build a Docker image when the code merges on `main`. Log-in to Google Cloud Run and deploy the latest image.
