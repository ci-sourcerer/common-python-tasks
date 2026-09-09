# `poe build`

Build the project and its containers.

**Category:** [`container-images`](../container-images.md)

**Tags:** `common`, `containers`, `packaging`

## Usage

```shell
poe build [--debug] [--no-cache] [--plain] [--single-arch] [--container-env CONTAINER_ENV...] [--container-envfile CONTAINER_ENVFILE...]
```

## Arguments

| Argument | Type | Description | Default |
| - | - | - | - |
| `--debug` | `boolean` | Build the debug image. | `false` |
| `--no-cache` | `boolean` | Do not use cache when building the image. | `false` |
| `--plain` | `boolean` | Do not pretty-print output. | `false` |
| `--single-arch` | `boolean` | Build images for a single architecture. | `false` |
| `--container-env` | `string, repeatable` | Inline container environment variables as repeated KEY=VALUE values. | — |
| `--container-envfile` | `string, repeatable` | Repeated list of container environment files. | — |