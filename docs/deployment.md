# Deployment

This page covers Sentry's own deployment of the app and its GitHub App. Users installing the GitHub App don't need it.

## Backend deployment

The app runs on Google Cloud Run. Google Cloud Build builds a Docker image when code merges to `main`. To release it, log in to Google Cloud Run and deploy the latest image. The GitHub App's webhook URL points at this deployment.

A Sentry project tracks errors of the backend itself. Its DSN is `APP_DSN`.

### Environment variables

| Variable | Purpose |
| --- | --- |
| `APP_DSN` | Optional. Reports the app's own errors and performance to Sentry. |
| `GH_WEBHOOK_SECRET` | Secret shared with the GitHub webhook. When unset, the app accepts unsigned requests. Generate one with `python3 -c 'import secrets; print(secrets.token_urlsafe(20))'`. |
| `GH_APP_ID` | GitHub App ID, shown on the GitHub App page. Setting it turns on GitHub App mode. |
| `GH_APP_PRIVATE_KEY` | Base64-encoded GitHub App private key. On Cloud Run (`K_SERVICE` set) without this variable, the app reads the key from Google Secret Manager instead. See `get_gh_app_private_key` in `src/web_app_handler.py`. |
| `GH_TOKEN` | Optional personal access token. The app uses it when `GH_APP_ID` is unset or the private key fails to load. |
| `COMMIT_TRACES_ENABLED` | Set to `true` or `1` to send `ci.commit` transactions. Requires the **Workflow run** event subscription. |
| `LOGGING_LEVEL` | Optional Python logging level. Defaults to `INFO`. |
| `FLASK_ENV` | Sets the `APP_DSN` environment. Defaults to `production`. `development` adds the `/debug-sentry` route. |

## Configure the GitHub App

Only Sentry GitHub admins can change the app.

1. Set the webhook URL to the backend deployment.
2. Set the webhook secret to the deployment's `GH_WEBHOOK_SECRET`.
3. Set the permissions:
   - Actions (workflows, workflow runs, and artifacts): read-only.
   - Single file: `sentry_config.ini`.
4. Subscribe to the [Workflow job](https://docs.github.com/en/webhooks/webhook-events-and-payloads#workflow_job) event. To send commit traces, also subscribe to [Workflow run](https://docs.github.com/en/webhooks/webhook-events-and-payloads#workflow_run).
5. Under "Private keys", select "Generate a private key". GitHub downloads a `.pem` file.
6. Run `base64 -i <path_to_pem_file>` and set the output as `GH_APP_PRIVATE_KEY` on the deployment. Delete the `.pem` file.
7. Set `GH_APP_ID` on the deployment.
8. Select "Install App", install it on your GitHub org, and grant access to "All repositories".
