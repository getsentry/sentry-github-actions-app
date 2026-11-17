# Local development

## Set up

Install [uv](https://docs.astral.sh/uv/) (`brew install uv`). If you use direnv, `.envrc` syncs `.venv`, activates it, and installs the pre-commit hooks. Otherwise, run:

```shell
uv sync
source .venv/bin/activate
pre-commit install
```

`uv sync` installs the Python version that `pyproject.toml` requires if you don't have it, and the dependencies pinned in `uv.lock`.

To add or upgrade a dependency, use `uv add <package>` (`uv add --dev <package>` for dev tools) or `uv lock --upgrade-package <package>`, and commit `uv.lock`.

## Commands

| Command | Description |
| --- | --- |
| `flask run -p 5001` | Start the app on <http://localhost:5001>. `.flaskenv` sets `FLASK_APP=src.main`. |
| `pytest` | Run the tests, as CI does. |
| `pytest --cov=src --cov-report=html` | Generate a coverage report. |
| `mypy` | Type check the code in strict mode, as CI does. |
| `pre-commit run --all-files` | Run the lint and format hooks, as CI does. |

## Ingest a single job

`cli.py` sends one job's trace without webhooks. It runs in GitHub App mode, so set `GH_APP_ID` and `GH_APP_PRIVATE_KEY` first. See [deployment.md](deployment.md#environment-variables).

```shell
python3 cli.py "https://github.com/getsentry/sentry/runs/5759197422" --installation-id <id>
```

The argument must be a job URL. For a job in the `getsentry` org, you can set `INSTALLATION_ID` instead of passing `--installation-id`.

## Receive webhooks locally

1. Start the app with `flask run -p 5001`.
2. Start ngrok with `ngrok http 5001` and note the URL.
3. Create a separate GitHub App for development, configured as in [deployment.md](deployment.md#configure-the-github-app), with its webhook URL set to the ngrok URL.
4. Generate a private key for it and set `GH_APP_ID`, `GH_APP_PRIVATE_KEY`, and the app's webhook secret as `GH_WEBHOOK_SECRET` locally. Put secrets in `.env`, which `.envrc` loads.
5. Delete the private key from the GitHub App when you finish.

Fixtures can carry old timestamps. Sentry then shows "Clock drift detected in SDK" on the transaction. You can ignore it.
