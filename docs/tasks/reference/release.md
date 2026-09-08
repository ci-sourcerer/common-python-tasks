# `poe release`

Run a full release flow for package and containers.

**Category:** [`packaging-and-releases`](../packaging-and-releases.md)

**Tags:** `common`, `containers`, `packaging`, `release`

## Usage

```shell
poe release [--component COMPONENT] [--stage STAGE] [--dry-run] [--debug] [--no-cache] [--plain] [--single-arch] [--container-env CONTAINER_ENV...] [--container-envfile CONTAINER_ENVFILE...] [--assets ASSETS...] [--repository REPOSITORY] [--repository-url REPOSITORY_URL] [--pre-script PRE_SCRIPT] [--post-script POST_SCRIPT]
```

## Arguments

| Argument | Type | Description | Default |
| - | - | - | - |
| `--component` | `string` | The version component to bump: major, minor, or patch. | `auto` |
| `--stage` | `string` | Optional pre-release stage to apply: alpha, beta, or rc. | — |
| `--dry-run` | `boolean` | Only perform a dry-run version bump. | `false` |
| `--debug` | `boolean` | Build/push debug container image tags when releasing containers. | `false` |
| `--no-cache` | `boolean` | Do not use cache when building container images. | `false` |
| `--plain` | `boolean` | Do not pretty-print container build output. | `false` |
| `--single-arch` | `boolean` | Build container image for a single architecture. | `false` |
| `--container-env` | `string, repeatable` | Inline container environment variables as repeated KEY=VALUE values. | — |
| `--container-envfile` | `string, repeatable` | Repeated list of container environment files. | — |
| `--assets` | `string, repeatable` | Optional repeated list of release asset patterns or paths. | — |
| `--repository` | `string` | Optional configured repository name to publish to. | — |
| `--repository-url` | `string` | Optional repository upload URL to publish to. | — |
| `--pre-script` | `string` | Optional shell command to run before the release steps. | — |
| `--post-script` | `string` | Optional shell command to run after the release completes. | — |