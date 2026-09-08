# `poe build-image`

Build the container image for this project using the Dockerfile template.

**Category:** [`container-images`](../container-images.md)

**Tags:** `build`, `containers`

## Usage

```shell
poe build-image [DOCKER_BUILD_ARGS...] [--debug] [--no-cache] [--plain] [--single-arch] [--dockerfile-hook-path DOCKERFILE_HOOK_PATH] [--container-env CONTAINER_ENV...] [--container-envfile CONTAINER_ENVFILE...]
```

## Arguments

| Argument | Type | Description | Default |
| - | - | - | - |
| `docker_build_args...` | `string, repeatable` | Additional arguments passed directly to `docker build`. Provide them after the task's `--` separator. Overrides `CONTAINER_DOCKER_BUILD_ARGS` when provided. | — |
| `--debug` | `boolean` | Build the debug image. | `false` |
| `--no-cache` | `boolean` | Do not use cache when building the image. | `false` |
| `--plain` | `boolean` | Do not pretty-print output. | `false` |
| `--single-arch` | `boolean` | Build images for a single architecture. | `false` |
| `--dockerfile-hook-path` | `string` | Optional executable script path that can mutate the generated Dockerfile before build. Overrides CONTAINER_DOCKERFILE_HOOK_PATH if provided. | — |
| `--container-env` | `string, repeatable` | Builder and runtime environment declarations as repeated KEY=VALUE values. | — |
| `--container-envfile` | `string, repeatable` | Optional repeated list of files containing builder and runtime environment declarations. | — |