# Sentry GitHub Actions App

[![codecov](https://codecov.io/gh/getsentry/sentry-github-actions-app/branch/main/graph/badge.svg?token=LVWHH6NYTF)](https://codecov.io/gh/getsentry/sentry-github-actions-app)

**NOTE**: If this is a project you would like us to invest in, please let us know in [this issue](https://github.com/getsentry/sentry-github-actions-app/issues/46). You can try this app by following the steps in the "Try it out" section below.

[This app](https://github.com/apps/sentry-github-app-alpha) allows your organization to instrument GitHub Actions with Sentry. You can use this to get insights of what parts of your CI are slow or failing often.

It works by listening to GitHub workflow events via a webhook configured in a GitHub App. These events are then stored in Sentry as performance transactions. The best value for this project is when you have [Sentry's Discover](https://docs.sentry.io/product/discover-queries/) and [Dashboards](https://docs.sentry.io/product/dashboards/) in order to slice the data and answer the questions you care about. In a sense, this project turns GitHub's CI into an app which Sentry monitors, thus, you can use many of the features you're already familiar with.

**NOTE**: The Discover feature is only available on either a Business or Trial Plan.

**NOTE**: The Dashboards feature is only available on the Team Plan or higher.

There's likely products out there that can give you insights into GitHub's CI, however, this may be cheaper, it saves you having to add another vendor and your developers are already familiar with using Sentry.

## Examples

This screenshot shows that you can group GitHub Actions through various tags in Sentry's Discover:

<img width="711" alt="image" src="https://user-images.githubusercontent.com/44410/175557087-2ca904e1-d815-4ae0-a6a1-01b4ca38323a.png">

This screenshot shows the transaction view for an individual GitHub Action showing each step of the job:

<img width="992" alt="image" src="https://user-images.githubusercontent.com/44410/175558737-7eca4036-73ce-4ed2-8b5a-51b5d882a814.png">

## Features

Here's a list of benefits you will get if you use this project:

- Visualize a GitHub job and the breakdown per step
  - For instance, it makes it easy to see what percentage of the jobs are dedicated to set up versus running tests
- Create CI alerts
  - For instance, if your main branch has a failure rate above a certain threshold
  - Notice when `on: schedule` workflows fail which currently GitHub does not make it easy to notice
- Create widgets and dashboards showing your CI data
  - For instance you can show: slowest jobs, most failing jobs, jobs requirying re-runs, repos consuming most CI
  - Some of the main tags by which you can slice the data: workflow file, repo, branch, commit, job_status, pull_request, run_attempt

Watch this video showing the features described above:

https://user-images.githubusercontent.com/44410/187217254-ad7c2eba-f4d4-4a08-9733-54cf92f466ec.mp4

## Try it out

Steps to follow:

1. Create a Sentry project to gather your GitHub CI data
   1. You don't need to select a platform in the wizard or any alerts
   2. Find the DSN key under the settings of the project you created
2. Create a private repo named `.sentry`
3. Create a file in that repo called `sentry_config.ini` with these contents (adjust your DSN value)

```ini
[sentry-github-actions-app]
; DSN value of the Sentry project you created in step (1) above.
dsn = https://foo@bar.ingest.sentry.io/foobar
```

   - **Note:** The app caches this file, so changes to it can take up to 10 minutes to apply.

4. Install [this GitHub App](https://github.com/apps/sentry-github-app-alpha)
   1. **"All repositories"** - this is the easiest option; all repositories will have telemetry from GitHub Actions sent.
   2. **"Only select repositories"**
      1. Ensure that the `.sentry` private repository (created in step 2 above) is selected
      2. Select any projects that are desired to have telemetry from all containing GitHub Actions sent.
   - **Note:** Regardless of which is selected, we only request **workflow jobs** and a **single file** permissions.

**NOTE**: In other words, we won't be able to access any of your code.

### Commit to green (optional)

Job traces tell you how long each job took, but not how long a commit waited for CI to go green. The app can also send one `ci.commit` transaction per green commit, lasting from its first workflow run being created until the last of its workflow runs passed (re-runs included, tagged `rerun:true`).

To turn it on:

1. Set `COMMIT_TRACES_ENABLED=true` on the deployment
2. Subscribe the GitHub App to **Workflow run** events (no new permissions needed)
3. Optionally, list the workflows that gate a commit in `sentry_config.ini`. By default every workflow run for the commit has to pass.

```ini
[sentry-github-actions-app]
dsn = https://foo@bar.ingest.sentry.io/foobar
; Workflow files that have to pass for a commit to count as green
commit_workflows = backend.yml, frontend.yml, acceptance.yml
```

Then chart, for example, `p50(transaction.duration)` for `transaction.op:ci.commit event:push branch:master` (master) or `event:pull_request` (PRs). Each successful run of a listed workflow costs one GitHub API call; failed and skipped runs cost none.

## Get help

Report bugs and feedback in [issue #46](https://github.com/getsentry/sentry-github-actions-app/issues/46). To develop or deploy the app, start at [AGENTS.md](AGENTS.md).

## License

MIT. See [LICENSE](LICENSE).
