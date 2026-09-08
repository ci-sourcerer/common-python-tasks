# `poe build-deps-image`

Build only the container dependency collector image for this project.

**Category:** [`container-images`](../container-images.md)

**Tags:** `build`, `containers`

## Usage

```shell
poe build-deps-image [DOCKER_BUILD_ARGS...] [--no-cache] [--plain] [--single-arch]
```

## Arguments

| Argument | Type | Description | Default |
| - | - | - | - |
| `docker_build_args...` | `string, repeatable` | Additional arguments passed directly to `docker build`. Provide them after the task's `--` separator. Overrides `CONTAINER_DOCKER_BUILD_ARGS` when provided. | — |
| `--no-cache` | `boolean` | Do not use cache when building the deps image. | `false` |
| `--plain` | `boolean` | Do not pretty-print output. | `false` |
| `--single-arch` | `boolean` | Build images for a single architecture. | `false` |