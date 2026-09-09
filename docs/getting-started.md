# Getting started

## Add the development dependency

Add a released version of `common-python-tasks` from the root of a Python project.

```shell
uv add --dev common-python-tasks==0.10.3
```

Configure Poe to expose the standard task set.

```toml
[tool.poe]
include_script = "common_python_tasks:tasks()"
```

The default selection provides formatting, linting, testing, package builds, dependency updates, and release tasks.

```shell
poe format
poe lint
poe test
```

## Select optional task groups

Pass `include_tags` when a project needs optional workflows.

```toml
[tool.poe]
include_script = "common_python_tasks:tasks(include_tags=['common', 'docs', 'containers'])"
```

Use `exclude_tags` when a project wants nearly every group.

```toml
[tool.poe]
include_script = "common_python_tasks:tasks(exclude_tags=['fastapi'])"
```

Calling `tasks()` with no arguments selects only `common`. Passing an explicit empty `include_tags` sequence selects every task unless an exclusion removes it.

## Automated setup

The release helper adds the dependency and configures Poe. Download the helper for the exact release being installed, review it, and run it with the same version.

```shell
curl --fail --silent --show-error --location \
  --output /tmp/add_common_python_tasks.py \
  https://raw.githubusercontent.com/ci-sourcerer/common-python-tasks/v0.10.3/scripts/add_common_python_tasks.py
```

```shell
COMMON_PYTHON_TASKS_VERSION=0.10.3 python3 /tmp/add_common_python_tasks.py
```

## Inspect available tasks

Poe displays the tasks selected by the project.

```shell
poe --help
```

The package module also lists its public default tasks. Set the log level to include their descriptions.

```shell
COMMON_PYTHON_TASKS_LOG_LEVEL=DEBUG python -m common_python_tasks
```

Continue with the [task reference](tasks/index.md) for task-specific behavior and requirements.
