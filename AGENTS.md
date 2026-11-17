# AGENTS.md

Flask app that receives GitHub `workflow_job` and `workflow_run` webhooks and sends them to Sentry as transactions. User docs are in [README.md](README.md).

## Commands

- Install: `uv sync`
- Test: `uv run pytest`
- Type check: `uv run mypy` (strict, over `src`, `tests`, and `cli.py`)
- Lint and format: `uv run pre-commit run --all-files`

## Invariants

- Dependencies live in `pyproject.toml` and are locked in `uv.lock`. Change them with `uv add`, `uv remove`, or `uv lock --upgrade-package`, and commit `uv.lock`. CI and the Docker image install with `--locked`, so a stale lockfile fails them.

## Docs

| Topic | Doc |
| --- | --- |
| Local setup, commands, `cli.py`, local webhooks | [docs/development.md](docs/development.md) |
| Cloud Run deployment, environment variables, GitHub App config | [docs/deployment.md](docs/deployment.md) |
| GitHub App post-installation page | [GithubAppPostInstall.md](GithubAppPostInstall.md) |
