# Github actions Sentry app

This app allows your organization to trace Github Actions with Sentry. You can use this to get insight of what parts of your CI is slow or failing often.
It works by listening to a Github webhook that sends workflows events and stores the data as performance transactions in Sentry.

## Set up

### Sentry

* Create a project for reporting errors of the app and another one to track Github workflow transactions.

### Github token & webhook

* Create a [personal token](https://github.com/settings/tokens)
  * You do not need to give it any scopes
  * Take note of the token (Regenerate it if you forgot to take note of it)
  * After creating the token, some orgs [require authorizing tokens](https://docs.github.com/en/enterprise-cloud@latest/authentication/authenticating-with-saml-single-sign-on/authorizing-a-personal-access-token-for-use-with-saml-single-sign-on), thus, select "Configure SSO" if you see it
  * If this is for development, you can place the token in a file named `.env` as `GH_TOKEN`
* Create a Github webhook for the repo you want to analyze
  * Choose `application/json`
  * Choose `workflow` events
  * Enter the Github token from the previous step

### Production/staging environment

* Deploy the app to a service (e.g. GCP) and make it publicly reachable
* Take note of the app's URL

### Local development

Prerequisites:

* [PDM](https://pdm.fming.dev/#installation) ([Helper script](https://gist.github.com/armenzg/4d2ac94bd770879d8df37c5da0fc7a33)) to manage Python requirements
* ngrok (for local dev)

Set up steps:

* Install ngrok, authenticate and start it up (`ngrok http 5000`)
* Take note of the URL
* Create a Github webhook for the repo you want to analyze
  * Choose `workflow` events & make sure to choose `application/json`

Development steps:

* Start the flask app (`pdm run start`)

Run tests with `pdm run test`.
