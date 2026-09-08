# Daily development

These tasks form the short feedback loop for ordinary Python changes. They are part of the default `common` task selection and use project-local Ruff, pytest, and coverage configuration before falling back to the package defaults.

Run formatting before linting so the checks operate on normalized source.

```shell
poe format
poe lint
poe test
```

See [Configuration](../configuration.md#configuration-precedence) for configuration discovery and diagnostic logging.

<!-- generated-task-reference -->

| Task | Description |
| - | - |
| [`test`](reference/test.md) | Run the test suite with coverage (if pytest-cov is installed). |
| [`clean`](reference/clean.md) | Clean up temporary files and directories. |
| [`format`](reference/format.md) | Fix import issues and format Python code with Ruff. |
| [`lint`](reference/lint.md) | Check Python lint and formatting with Ruff. |

<!-- end-generated-task-reference -->
