# Documentation

Documentation tasks are selected with the optional `docs` tag and require a project-owned `zensical.toml` and documentation source directory. Production builds always use Zensical's strict mode so warnings fail CI.

The local server watches documentation and configuration changes until interrupted.

```shell
poe docs-serve --open-browser
```

See [Documentation workflows](../documentation-workflows.md) for artifact uploads, pull-request previews, and production deployment.

<!-- generated-task-reference -->

| Task | Description |
| - | - |
| [`docs-build`](reference/docs-build.md) | Build the Zensical documentation site in strict mode. |
| [`docs-serve`](reference/docs-serve.md) | Serve the Zensical documentation site for local preview. |

<!-- end-generated-task-reference -->
