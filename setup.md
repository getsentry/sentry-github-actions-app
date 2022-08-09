# Set-up

This page includes information about our deployment. No need to be read by customers installing the Github App.

## Backend deployment

In Sentry.io, we created a project to track errors of the backend itself (`APP_DSN` in section below).

The app is deployed via GC. The app's deployment is in the webhook url for the Github app. Currently the deployment requires manual intervention.

Common environment variables:

- `APP_DSN`: Report your deployment errors to Sentry
- `GH_WEBHOOK_SECRET`: Secret shared between Github's webhook and your app
  - Create a secret with `python3 -c 'import secrets; print(secrets.token_urlsafe(20))'` on your command line
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
  - Convert it into a single line value by using base64 (`base64 -i path_to_pem_file`) and delete it

For local development, you need to make the App's webhook point to your ngrok set up. You should create a new private key (a .pem file that gets automatically downloaded when generated) for your local development and do not forget to delete the private key when you are done.

## The Github App

**NOTE**: Only Sentry Github Admins can make changes to the app

Configuration taken after creating the app:

- Configure the Webhook URL to point to the backend deployment
- Set the Webhook Secret to be the same as the backend deployment
- Set the following permissions for the app:
  - Actions: Workflows, workflow runs and artifacts -> Read-only
  - Singe File: sentry_config.ini
  - Subscribe to events:
    - [Workflow job](https://docs.github.com/en/developers/webhooks-and-events/webhooks/webhook-events-and-payloads#workflow_job)

After completing the creation of the app you will need to make few more changes:

- Click on `Generate a private key`
  - Run `base64 -i <path_to_download_file>`
  - Add to the deployment the variable `GH_APP_PRIVATE_KEY`
  - Delete the file just downloaded
- Add to the deployment the variable `GH_APP_ID`
- Select "Install App" and install the app on your Github org
  - Grant access to "All Repositories"
- Look at the URL of the installation and you will find the installation ID
  - Add to the deployment the variable `GH_APP_INSTALLATION_ID`
