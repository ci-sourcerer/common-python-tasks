# Packaging and releases

Packaging tasks use uv for dependency updates, builds, and publication. Release tasks derive versions from project metadata and Git history, can update the changelog, and can publish GitHub Releases.

Release operations expect a clean working tree and the repository's default branch unless their documented options explicitly allow otherwise. Use dry-run modes before changing tags or publishing artifacts.

Publish targets and release hooks are described in [Configuration](../configuration.md#project-and-publishing-settings).

<!-- generated-task-reference -->

| Task | Description |
| - | - |
| [`publish-package`](reference/publish-package.md) | Publish the package to the PyPI server. |
| [`publish-github-release`](reference/publish-github-release.md) | Publish or update a GitHub Release for the current repository. |
| [`update-dependencies`](reference/update-dependencies.md) | Update project dependencies with uv. |
| [`build-package`](reference/build-package.md) | Build the package (wheel and sdist). |
| [`bump-version`](reference/bump-version.md) | Bump the project version. |
| [`changelog`](reference/changelog.md) | Print the changelog for the current version based on git history and git-cliff. |
| [`release`](reference/release.md) | Run a full release flow for package and containers. |

<!-- end-generated-task-reference -->
