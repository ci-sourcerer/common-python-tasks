# `poe bump-version`

Bump the project version.

**Category:** [`packaging-and-releases`](../packaging-and-releases.md)

**Tags:** `common`, `packaging`

## Usage

```shell
poe bump-version [--component COMPONENT] [--stage STAGE] [--dry-run] [--allow-dirty]
```

## Arguments

| Argument | Type | Description | Default |
| - | - | - | - |
| `--component` | `string` | The version component to bump: major, minor, patch, or auto to infer the bump from git history using git-cliff. | `auto` |
| `--stage` | `string` | Optional pre-release stage to apply: alpha, beta, or rc. | — |
| `--dry-run` | `boolean` | Print what would happen without making changes. | `false` |
| `--allow-dirty` | `boolean` | Allow version bumping with uncommitted changes. | `false` |