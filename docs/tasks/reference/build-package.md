# `poe build-package`

Build the package (wheel and sdist).

**Category:** [`packaging-and-releases`](../packaging-and-releases.md)

**Tags:** `build`, `common`, `packaging`

## Usage

```shell
poe build-package [--wheel-only] [--clean-dist]
```

## Arguments

| Argument | Type | Description | Default |
| - | - | - | - |
| `--wheel-only` | `boolean` | Whether to build only the wheel artifact. | `false` |
| `--clean-dist` | `boolean` | Whether to remove existing distribution artifacts first. | `false` |