# `poe run-container`

Run the Docker image as a container for this project.

**Category:** [`container-images`](../container-images.md)

**Tags:** `containers`

## Usage

```shell
poe run-container [--tag TAG] [--entrypoint ENTRYPOINT] [--command COMMAND] [--root] [--echo-env] [--env ENV...] [--envfile ENVFILE...] [--privileged] [--volumes VOLUMES...]
```

## Arguments

| Argument | Type | Description | Default |
| - | - | - | - |
| `--tag` | `string` | Image tag to run. Default: Use the most-recently-built tag. | — |
| `--entrypoint` | `string` | Optional entrypoint override. | — |
| `--command` | `string` | Optional command to pass to the entrypoint. | — |
| `--root` | `boolean` | Whether to run as root (only relevant with a shell entrypoint). | `false` |
| `--echo-env` | `boolean` | Whether to prepend an env dump to the command. | `false` |
| `--env` | `string, repeatable` | Repeated KEY=VALUE or KEY values to pass with -e. | — |
| `--envfile` | `string, repeatable` | Repeated envfile paths to pass with --env-file. | — |
| `--privileged` | `boolean` | Whether to run the container with --privileged. | `false` |
| `--volumes` | `string, repeatable` | Repeated volume mounts to pass with -v. | — |