# Task reference

The task reference is divided by workflow. Each category page includes a table linking to individual task pages with complete command syntax, tags, accepted arguments, defaults, and descriptions taken directly from the packaged Poe configuration and Python task docstrings.

## Browse by category

| Section | Purpose |
| - | - |
| [Daily development](daily-development.md) | Format, lint, test, and clean a project |
| [Documentation](documentation.md) | Build and locally serve a Zensical site |
| [Packaging and releases](packaging-and-releases.md) | Build, version, publish, and release packages |
| [Container images](container-images.md) | Build, run, inspect, and publish images |
| [Development stacks](development-stacks.md) | Operate the FastAPI and PostgreSQL Compose stack |

Individual task reference pages are also available in the sidebar under the "reference" section.

## Configuration

The `common` tag is selected when `tasks()` is called without arguments. Enable optional workflows by passing their tags to `include_tags`.

```toml
[tool.poe]
include_script = "common_python_tasks:tasks(include_tags=['common', 'docs', 'containers'])"
```

Run `poe --help TASK_NAME` in a consuming project to inspect the installed release's command-line help.

## Generated documentation references

Task sections and the container Dockerfile templates are generated from the current package source. After changing task metadata, arguments, or a template, refresh the pages and verify the result.

```shell
poe update-docs-references
poe check-docs-references
```

The documentation workflows run the check task before building the site, so stale references fail CI.
