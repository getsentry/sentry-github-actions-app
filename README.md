# Github actions Sentry app

This app allows your organization to trace Github Actions with Sentry. You can use this to get insight of what parts of your CI is slow or failing often.
It works by listening to a Github webhook that sends workflows events and stores the data as performance transactions in Sentry.

## Set up

### Sentry

* Create a project for reporting errors of the app and another one to track Github workflow transactions.

### Create Github token

* Create a [personal token](https://github.com/settings/tokens)
  * You do not need to give it any scopes
  * Take note of the token (Regenerate it if you forgot to take note of it)
  * After creating the token, some orgs [require authorizing tokens](https://docs.github.com/en/enterprise-cloud@latest/authentication/authenticating-with-saml-single-sign-on/authorizing-a-personal-access-token-for-use-with-saml-single-sign-on), thus, select "Configure SSO" if you see it
  * If this is for development, you can place the token in a file named `.env` as `GH_TOKEN`

### Create Github webhook

* Create a Github webhook for the repo you want to analyze from the settings UI of the repo
  * Choose `application/json`
  * Choose `workflow` events
  * Enter the Github token from the previous step
  * Enter the URL of a deployed app or use an ngrok URL for local development

### App deployment

* Deploy the app to a service (e.g. GCP) and make it publicly reachable
* Take note of the app's URL and use it when creating the Github webhook
* You will have to set env variable for the app named `GH_TOKEN`

### Local development

Prerequisites:

* [PDM](https://pdm.fming.dev/#installation) ([Helper script](https://gist.github.com/armenzg/4d2ac94bd770879d8df37c5da0fc7a33)) to manage Python requirements
* ngrok (for local dev)

You can ingest a single job without webhooks or starting the app by using the cli. For example:

```shell
# This is a normal URL of a job on Github
pdm run ingest https://github.com/getsentry/sentry/runs/5759197422?check_suite_focus=true
# This is desgined to test processing a Github webhook event
pdm run ingest tests/fixtures/failed_workflow.json
```

Steps to ingest events from a repository:

* Install ngrok, authenticate and start it up (`ngrok http 5000`)
  * Take note of the URL
* Create a Github webhook for the repo you want to analyze
  * Choose `workflow` events & make sure to choose `application/json`
  * Put Ngrok's URL there

Development steps:

* Start the flask app (`pdm run start`)

Run tests with `pdm run test`.
