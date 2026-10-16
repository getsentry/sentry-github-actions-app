# AGENTS.md

Flask app that receives GitHub `workflow_job` and `workflow_run` webhooks and sends them to Sentry as transactions. User docs are in [README.md](README.md).

## Commands

- Install: `pip install -r requirements.txt -r requirements-dev.txt`
- Test: `pytest` (CI runs `tox`)
- Lint and format: `pre-commit run --all-files`

## Invariants

- `requirements.txt` holds direct dependencies. The Docker image installs `requirements.frozen.txt`, so update both.

## Docs

| Topic | Doc |
| --- | --- |
| Local setup, commands, `cli.py`, local webhooks | [docs/development.md](docs/development.md) |
| Cloud Run deployment, environment variables, GitHub App config | [docs/deployment.md](docs/deployment.md) |
| GitHub App post-installation page | [GithubAppPostInstall.md](GithubAppPostInstall.md) |
