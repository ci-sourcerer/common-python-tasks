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

## Deploy a single documentation site to GitHub Pages

Enable GitHub Actions as the repository's Pages source. A default-branch caller can then select production deployment. Existing callers continue to use this mode when `docs_version` is empty.

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

## Deploy versioned documentation to GitHub Pages

Versioned deployment uses the Zensical-compatible `mike` fork. The workflow keeps generated versions on a Git branch and publishes the assembled branch through GitHub Actions, so the repository's Pages source remains GitHub Actions. The fork is a transitional dependency until Zensical provides native versioning support.

Enable the version selector in `zensical.toml`.

```toml
[project.extra.version]
provider = "mike"
default = ["latest", "dev"]

[project.plugins.mike]
alias_type = "redirect"
```

Pass a version identifier when deploying. The caller must grant `contents: write` so the workflow can update the versions branch.

```yaml
jobs:
  docs:
    uses: ci-sourcerer/common-python-tasks/.github/workflows/docs.yml@v0.12.1
    with:
      python_version: '3.14'
      dependency_group: dev
      deploy_github_pages: true
      docs_version: '2.4'
      docs_version_title: '2.4.3'
      docs_aliases: '["latest"]'
      docs_default_version: latest
    permissions:
      contents: write
      pages: write
      id-token: write
```

`docs_aliases` must be a JSON array. Versions and aliases accept letters, digits, periods, underscores, and hyphens. The default versions branch is `gh-pages`; set `docs_versions_branch` to use another valid Git branch. The reusable workflow serializes updates to each repository and versions branch. Alias redirects are updated atomically with the version metadata, and versions not named by the current deployment remain unchanged.

The workflow still performs the strict `poe docs-build` check and uploads the current checkout as the normal Actions artifact. It then builds through `mike`, updates the versions branch, and gives the complete assembled site to GitHub Pages.

## Publish development and release versions

Use one serialized production workflow for default-branch and tag deployment. Publish the default branch as `dev`, and publish stable tags to a major/minor documentation series. For example, `v2.4.3` updates version `2.4`, uses `2.4.3` as its display title, moves the `latest` alias, and makes `latest` the site root. Later default-branch deployments update `dev` without moving the root away from `latest`.

The repository's own deployment workflow demonstrates this policy. Pull requests continue to use the unversioned artifact and Cloudflare preview flow, so a pull request previews the next `dev` site without modifying the versions branch.

## Backfill an existing release

A repository can expose manual workflow inputs that pass an older tag through `checkout_ref` while deploying it under an explicit documentation version. For this repository, run `docs-deploy` manually with values such as the following.

| Input | Value |
| - | - |
| `source_ref` | A tag that already enables the `mike` version selector, or empty to build the selected workflow ref |
| `docs_version` | `0.12` |
| `docs_version_title` | `0.12.1` |
| `update_latest` | `true` |
| `default_version` | `latest` |

Backfill supported series from oldest to newest so the selector order and `latest` alias finish in the desired state. Historical refs created before versioning was configured cannot produce a working selector without a compatible configuration change; build those docs from a suitable maintenance branch or the current branch instead. A normal default-branch deployment uses `dev` as the initial site root only when the versions branch has no root redirect, which keeps the documentation reachable before the first release or backfill.

## Maintain published versions

The versions branch contains `versions.json`, the generated version directories, aliases, and the root redirect. Inspect a local checkout with the same pinned Zensical-compatible fork before deleting or retitling published versions. Since the fork is installed directly from GitHub, changes to its pinned commit require a versioned workflow update and a representative multi-version build test.
