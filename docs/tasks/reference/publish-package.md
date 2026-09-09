# `poe publish-package`

Publish the package to the PyPI server.

**Category:** [`packaging-and-releases`](../packaging-and-releases.md)

**Tags:** `common`, `packaging`

## Usage

```shell
poe publish-package [--build-first] [--repository REPOSITORY] [--repository-url REPOSITORY_URL]
```

## Arguments

| Argument | Type | Description | Default |
| - | - | - | - |
| `--build-first` | `boolean` | Build the package before publishing. | `true` |
| `--repository` | `string` | Optional configured repository name to publish to. | — |
| `--repository-url` | `string` | Optional repository upload URL to publish to. | — |