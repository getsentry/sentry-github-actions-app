# Github actions Sentry app

This app allows your organization to trace Github Actions with Sentry. You can use this to get insight of what parts of your CI is slow or failing often.
It works by listening to a Github webhook that sends workflows events and stores the data as performance transactions in Sentry.

## Set up

### Production/staging environment

* Deploy the app to a service (e.g. GCP) and make it publicly reachable
* Take note of the app's URL
* Create a Github webhook for the repo you want to analyze
  * Choose `workflow` events & make sure to choose `application/json`

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

* Start the flask app (`pdm run flask`)

Run tests with `pdm run test`.
