# Common Python Tasks

`common-python-tasks` is a reusable collection of opinionated [Poe the Poet](https://poethepoet.natn.io/guides/packaged_tasks.html) tasks for Python projects. It gives projects one shared implementation for everyday development, packaging, releases, container images, development stacks, and documentation.

## Choose where to begin

- **Adding the package to a project?** Follow [Getting started](getting-started.md).
- **Looking for a command?** Browse the [task reference](tasks/index.md).
- **Customizing behavior?** Use the [configuration reference](configuration.md).
- **Publishing documentation like this?** See the [documentation workflows](documentation-workflows.md).

## Task groups

Tasks are organized by tags, so each project can select only the workflows it needs.

| Group | Purpose |
| - | - |
| `common` | Formatting, linting, testing, packaging, and releases |
| `docs` | Build and locally serve Zensical documentation |
| `containers` | Build, run, inspect, and publish container images |
| `fastapi` | Run a local FastAPI and PostgreSQL development stack |

The default task collection exposes the `common` group. Optional groups are enabled through the package's `include_script` expression.

```toml
[tool.poe]
include_script = "common_python_tasks:tasks(include_tags=['common', 'docs'])"
```

## Design approach

The package supplies executable workflows and conservative defaults. Project-specific source files remain in the consuming repository, including application code, documentation content, Zensical configuration, Docker extensions, and environment settings.

Commands run in the consuming project's environment, so the same task definitions work locally and in CI without hiding the underlying tools.
