# `poe publish-github-release`

Publish or update a GitHub Release for the current repository.

**Category:** [`packaging-and-releases`](../packaging-and-releases.md)

**Tags:** `common`, `packaging`, `release`

## Usage

```shell
poe publish-github-release [--tag-name TAG_NAME] [--release-name RELEASE_NAME] [--body BODY] [--prerelease] [--draft] [--assets ASSETS...]
```

## Arguments

| Argument | Type | Description | Default |
| - | - | - | - |
| `--tag-name` | `string` | Optional release tag to publish. | — |
| `--release-name` | `string` | Optional display name for the release. | — |
| `--body` | `string` | Optional release notes body. | — |
| `--prerelease` | `boolean` | Whether to mark the release as a pre-release. | `false` |
| `--draft` | `boolean` | Whether to create the release as a draft. | `false` |
| `--assets` | `string, repeatable` | Optional release asset paths or glob patterns. | — |