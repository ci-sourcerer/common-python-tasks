# `poe test`

Run the test suite with coverage (if pytest-cov is installed).

**Category:** [`daily-development`](../daily-development.md)

**Tags:** `common`, `test`

## Usage

```shell
poe test [PATHS...] [--quiet]
```

## Arguments

| Argument | Type | Description | Default |
| - | - | - | - |
| `paths...` | `string, repeatable` | Optional test file paths or directories to pass through to pytest. | — |
| `--quiet` | `boolean` | Run tests in a quieter mode. | `false` |