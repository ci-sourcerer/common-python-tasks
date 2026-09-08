# Documentation workflows

Projects can use the packaged documentation tasks locally and the repository's reusable GitHub workflow in CI. The workflow builds the caller's repository, not `common-python-tasks`.

## Configure a project

Add a `zensical.toml` file and select the `docs` task group.

```toml
[tool.poe]
include_script = "common_python_tasks:tasks(include_tags=['common', 'docs'])"
```

Build or serve the site locally.

```shell
poe docs-build
poe docs-serve
```

## Build pull-request artifacts

Keep event triggers and path filters in the consuming repository, then call the reusable workflow from a job.

```yaml
name: docs-preview

on:
  pull_request:
    paths:
      - 'docs/**'
      - 'zensical.toml'
      - 'pyproject.toml'
      - 'uv.lock'

jobs:
  docs:
    uses: ci-sourcerer/common-python-tasks/.github/workflows/docs.yml@v0.11.0
    with:
      python_version: '3.14'
      dependency_group: dev
    permissions:
      contents: read
```

The workflow uploads the rendered site as a GitHub Actions artifact by default.

## Run a client-owned generated-document check

Some projects generate additional documentation from application code. Keep that generator in the consuming project and pass its Poe check task to the workflow.

```yaml
with:
  python_version: '3.14'
  dependency_group: dev
  generated_docs_check_task: docs-cli-reference-check
```

Only task names containing letters, digits, underscores, and hyphens are accepted.

## Enable Cloudflare Pages previews

Cloudflare publication is optional. The workflow ensures that one Direct Upload Pages project exists for the consuming repository, then deploys previews to it with narrowly scoped credentials.

```yaml
jobs:
  docs:
    uses: ci-sourcerer/common-python-tasks/.github/workflows/docs.yml@v0.11.0
    with:
      python_version: '3.14'
      dependency_group: dev
      publish_cloudflare: true
      cloudflare_project_name: stacksmith-docs
      cloudflare_preview_domain: preview.example.com
      cloudflare_preview_zone: example.com
    permissions:
      contents: read
      deployments: write
    secrets:
      cloudflare_account_id: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
      cloudflare_api_token: ${{ secrets.CLOUDFLARE_API_TOKEN }}
```

The project is created on the first trusted pull request, using `main` as its production branch by default. Set `cloudflare_production_branch` if the repository uses a different default branch. Set `cloudflare_preview_domain` to publish previews at `pr-42.preview.example.com`; leave it empty to use `pr-42.stacksmith-docs.pages.dev`. Set `cloudflare_preview_zone` when the preview domain is a subdomain of the DNS zone. The API token needs Pages Write, Zone Read, and Zone DNS Edit permissions when custom preview domains are enabled. Fork pull requests receive the build artifact but are not published because repository secrets are unavailable. A separate `pull_request`-closed workflow can remove the custom hostname, its matching DNS record, and older deployments for that preview branch while preserving the shared Pages project. Cloudflare retains the latest branch deployment.

## Deploy production documentation to GitHub Pages

Enable GitHub Actions as the repository's Pages source. A default-branch caller can then select production deployment.

```yaml
jobs:
  docs:
    uses: ci-sourcerer/common-python-tasks/.github/workflows/docs.yml@v0.11.0
    with:
      python_version: '3.14'
      dependency_group: dev
      deploy_github_pages: true
    permissions:
      contents: read
      pages: write
      id-token: write
```

Pin the workflow to the release that matches the installed package. Pin an exact commit SHA when an immutable workflow reference is required.
