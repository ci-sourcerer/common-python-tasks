# `poe container-shell`

Run the debug image with an interactive shell.

**Category:** [`container-images`](../container-images.md)

**Tags:** `containers`, `debug`

## Usage

```shell
poe container-shell [--tag TAG] [--shell SHELL] [--root] [--no-echo-env] [--env ENV...] [--envfile ENVFILE...] [--privileged] [--volumes VOLUMES...]
```

## Arguments

| Argument | Type | Description | Default |
| - | - | - | - |
| `--tag` | `string` | Image tag to use. Default: Use the most-recently-built tag. | — |
| `--shell` | `string` | Preferred shell name or path. Default: Use the first available from zsh, fish, ksh, bash, and sh. | — |
| `--root` | `boolean` | Whether to run the shell as root. | `false` |
| `--no-echo-env` | `boolean` | Whether to suppress printing environment variables on startup for debugging. | `false` |
| `--env` | `string, repeatable` | Repeated KEY=VALUE or KEY values to pass with -e. | — |
| `--envfile` | `string, repeatable` | Repeated envfile paths to pass with --env-file. | — |
| `--privileged` | `boolean` | Whether to run the container with --privileged. | `false` |
| `--volumes` | `string, repeatable` | Repeated volume mounts to pass with -v. | — |