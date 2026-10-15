# Common Python Tasks

`common-python-tasks` provides reusable, opinionated [Poe the Poet](https://poethepoet.natn.io/guides/packaged_tasks.html) tasks for Python development, packaging, releases, containers, and documentation.

Read the [complete documentation](https://common-python-tasks.ci-sourcerer.com/) for the task reference, configuration options, and deployment guidance.

## Quick start

Add the package as a development dependency.

```shell
uv add --dev common-python-tasks==0.12.1
```

Expose the default task set in `pyproject.toml`.

```toml
[tool.poe]
include_script = "common_python_tasks:tasks()"
```

Run the everyday development tasks.

```shell
poe format
poe lint
poe test
```

## Optional workflows

Select additional task groups with `include_tags`.

```toml
[tool.poe]
include_script = "common_python_tasks:tasks(include_tags=['common', 'docs', 'containers'])"
```

| Tag | Purpose |
| - | - |
| `common` | Formatting, linting, testing, packaging, and releases |
| `docs` | Build and serve Zensical documentation |
| `containers` | Build, run, inspect, and publish container images |
| `fastapi` | Run the FastAPI and PostgreSQL development stack |

Documentation projects can build locally or start a development server.

```shell
poe docs-build
poe docs-serve
```

The [documentation workflow guide](https://common-python-tasks.ci-sourcerer.com/documentation-workflows/) covers GitHub Actions artifacts, optional Cloudflare Pages previews, and GitHub Pages deployment.

## Learn more

- [Getting started](https://common-python-tasks.ci-sourcerer.com/getting-started/)
- [Task reference](https://common-python-tasks.ci-sourcerer.com/tasks/)
- [Configuration reference](https://common-python-tasks.ci-sourcerer.com/configuration/)

The project is in alpha, so minor releases may contain breaking changes. It is distributed under the [MIT license](LICENSE).
