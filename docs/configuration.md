# Configuration

Every consuming project needs `pyproject.toml` and Poe the Poet. Tasks that build, publish, install, or update packages use uv.

## Configuration precedence

Pytest and coverage configuration is resolved in this order.

1. Matching `pyproject.toml` sections
2. Environment variables naming configuration files
3. Project-root configuration files
4. Defaults bundled with `common-python-tasks`

Ruff uses `RUFF_CONFIG` when set. Otherwise, it discovers `.ruff.toml`, `ruff.toml`, or `[tool.ruff]` in `pyproject.toml`. The bundled configuration is used when the project has no Ruff configuration.

## Project and publishing settings

| Setting | Purpose |
| - | - |
| `PACKAGE_NAME` | Override the package name inferred from `pyproject.toml` |
| `COMMON_PYTHON_TASKS_PUBLISH_REPOSITORY` | Select a named uv publish index |
| `COMMON_PYTHON_TASKS_PUBLISH_URL` | Select a uv upload URL |
| `GITHUB_RELEASE_ASSETS` | Select GitHub Release asset paths or glob patterns |
| `SKIP_GITHUB_RELEASE` | Disable GitHub Release publication |
| `RELEASE_UPDATE_CHANGELOG` | Generate and commit release changelog content |
| `RELEASE_PRE_SCRIPT` | Run a command before the release steps |
| `RELEASE_POST_SCRIPT` | Run a command after the release steps |

The package also recognizes uv's `UV_PUBLISH_INDEX` and `UV_PUBLISH_URL` settings. Explicit task arguments take precedence over environment values and project configuration.

## Container settings

Container variables are read by the host-side tasks unless their description explicitly says that they persist in the image. See [Container images](tasks/container-images.md) for the generated Dockerfile lifecycle, environment precedence, extensions, and dependency images.

### Image and build settings

| Setting | Purpose |
| - | - |
| `CONTAINER_REGISTRY_USERNAME` | Registry username used for image tags |
| `CONTAINER_REGISTRY_URL` | Registry hostname and optional namespace path; defaults to `docker.io/<username>` |
| `CONTAINER_REGISTRY_NAMESPACE` | Namespace appended when the registry URL contains only a hostname |
| `CONTAINER_PYTHON_VARIANT` | Python base-image variant; defaults to `slim`, while an empty value disables the suffix |
| `WORKDIR_PATH` | Home and working directory for the non-root `py` user; defaults to `/workspace` |
| `CONTAINER_APT_PACKAGES` | Space-delimited APT packages installed in the runtime stage |
| `CONTAINER_CUSTOM_ENTRYPOINT` | `[project.scripts]` key selected as the image entrypoint command |
| `CONTAINER_DOCKER_BUILD_ARGS` | Shell-tokenized arguments passed directly to `docker build`; task arguments after `--` take precedence |
| `CONTAINER_DOCKERFILE_HOOK_PATH` | Executable host script that modifies the rendered Dockerfile before the build |
| `CONTAINER_PRUNE_KEEP` | Prior images kept after a build; `-1` disables pruning, `0` keeps only the latest, and `N` keeps the latest plus `N` prior images |

### Environment and extension settings

| Setting | Purpose |
| - | - |
| `CONTAINER_ENV` | Colon-delimited `KEY=VALUE` declarations persisted in the builder, runtime, final, and debug images |
| `.containerenv` | Project-root file containing the same declarations, at the lowest precedence |
| `UV_INDEX_<NAME>_USERNAME` | Private uv index username passed to BuildKit as a secret rather than persisted in the image |
| `UV_INDEX_<NAME>_PASSWORD` | Private uv index password passed to BuildKit as a secret rather than persisted in the image |
| `CONTAINER_EXTENSION_FILES` | Colon-delimited local Dockerfile fragments appended to the runtime stage |
| `CONTAINER_EXTENSIONS` | Colon-delimited installed extension bundles, optionally written as `bundle=value` |

### Dependency-image settings

| Setting | Purpose |
| - | - |
| `CONTAINER_DEPS_CONTENT` | Inline instructions for the bundled dependency-image Dockerfile; takes precedence over dependency files |
| `CONTAINER_DEPS_FILE` | Colon-delimited complete dependency Dockerfiles used when inline content is unset |
| `CONTAINER_DEPS_IMAGE` | Existing image that exports artifacts through `/tmp/deps` |
| `CONTAINER_DEPS_MAPPINGS` | Whitespace-delimited `name:/destination/path` moves for content copied from `/tmp/deps` |
| `CONTAINER_DEPS_MOVE_SCRIPT` | Inline script that distributes copied dependency artifacts and takes precedence over mappings |
| `CONTAINER_DEPS_MOVE_SCRIPT_PATH` | Host path to a dependency move script; takes precedence over the inline script and mappings |

## Development-stack settings

Set `COMPOSE_TYPE=fastapi` to use the bundled FastAPI stack. Add PostgreSQL with `COMPOSE_ADDONS=db`.

```toml
[tool.poe.env]
COMPOSE_TYPE = "fastapi"
COMPOSE_ADDONS = "db"
API_PORT = "8080"
DB_PORT = "5432"
```

`COMPOSE_FILE` replaces automatic compose-file selection. `COMPOSE_OVERLAY_FILES` appends project-specific overlays to the automatically selected files.

## Diagnostics

Set `COMMON_PYTHON_TASKS_LOG_LEVEL=DEBUG` to show configuration resolution and subprocess commands.

```shell
COMMON_PYTHON_TASKS_LOG_LEVEL=DEBUG poe test
```

The complete environment-variable inventory remains available in the repository [README](https://github.com/ci-sourcerer/common-python-tasks#environment-variables).
