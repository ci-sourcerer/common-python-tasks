# `poe update-dependencies`

Update project dependencies with uv.

**Category:** [`packaging-and-releases`](../packaging-and-releases.md)

**Tags:** `common`, `packaging`

## Usage

```shell
poe update-dependencies [DEPENDENCIES...] [--branch] [--branch-name BRANCH_NAME] [--commit] [--pr] [--draft] [--run-tests]
```

## Arguments

| Argument | Type | Description | Default |
| - | - | - | - |
| `dependencies...` | `string, repeatable` | Optional dependency names to update. When omitted, update all dependencies. | — |
| `--branch` | `boolean` | Create a dependency update branch after updating. | `false` |
| `--branch-name` | `string` | Optional branch name to use instead of generating one. | — |
| `--commit` | `boolean` | Commit the dependency update files. | `false` |
| `--pr` | `boolean` | Create and push a branch, commit the changes, and open a GitHub pull request. | `false` |
| `--draft` | `boolean` | Create the pull request as a draft. | `false` |
| `--run-tests` | `boolean` | Run the test task before committing. | `false` |