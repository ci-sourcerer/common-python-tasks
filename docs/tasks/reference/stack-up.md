# `poe stack-up`

Bring up the development stack for the application.

**Category:** [`development-stacks`](../development-stacks.md)

**Tags:** `containers`, `fastapi`, `web`

## Usage

```shell
poe stack-up [--debug] [--no-cache] [--detach] [--services SERVICES...] [--container-env CONTAINER_ENV...] [--container-envfile CONTAINER_ENVFILE...]
```

## Arguments

| Argument | Type | Description | Default |
| - | - | - | - |
| `--debug` | `boolean` | Enable debug mode (auto-loads all *-debug.yml compose files). | `false` |
| `--no-cache` | `boolean` | Do not use cache when building the image. | `false` |
| `--detach` | `boolean` | Run the stack in detached mode. | `false` |
| `--services` | `string, repeatable` | Optional repeated list of services to start. If not provided, all services will be started. | — |
| `--container-env` | `string, repeatable` | Inline container environment variables as repeated KEY=VALUE values. | — |
| `--container-envfile` | `string, repeatable` | Repeated list of container environment files. | — |