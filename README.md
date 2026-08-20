# Common Python Tasks

`common-python-tasks` provides reusable, opinionated [Poe the Poet](https://poethepoet.natn.io/guides/packaged_tasks.html) tasks for common Python development workflows.

It supplies sensible defaults for formatting, linting, testing, packaging, releases, and container workflows while allowing projects to override configuration when needed.

## Quick start

### Manual setup

Add `common-python-tasks` as a development dependency from your project root.

```shell
uv add --dev common-python-tasks==0.10.0
```

Configure Poe the Poet to expose the default `common` task set.

```toml
[tool.poe]
include_script = "common_python_tasks:tasks()"
```

Run the common development tasks.

```shell
poe format
poe lint
poe test
```

### Automated setup

The helper script performs the same development-dependency installation and Poe configuration. Download the script for the exact release you want, review it, then run it from your project root.

```shell
curl --fail --silent --show-error --location \
  --output /tmp/add_common_python_tasks.py \
  https://raw.githubusercontent.com/ci-sourcerer/common-python-tasks/v0.10.0/scripts/add_common_python_tasks.py
```

Review the downloaded script before executing it.

```shell
less /tmp/add_common_python_tasks.py
```

Run the reviewed script with the same pinned package version.

```shell
COMMON_PYTHON_TASKS_VERSION=0.10.0 python3 /tmp/add_common_python_tasks.py
```

To install another release, replace both occurrences of `0.10.0` with that release's version.

## Available tasks

The generated tables below list public tasks only. Tags identify which tasks are selected by `include_tags` and `exclude_tags`.

<!-- tasks-table -->

### Daily development

| Task | Description | Tags |
| --- | --- | --- |
| `test` | Run the test suite with coverage (if pytest-cov is installed). | common, test |
| `clean` | Clean up temporary files and directories. | clean, common |
| `format` | Fix import issues and format Python code with Ruff. | common, format |
| `lint` | Check Python lint and formatting with Ruff. | common, lint |

### Packaging and releases

| Task | Description | Tags |
| --- | --- | --- |
| `publish-package` | Publish the package to the PyPI server. | common, packaging |
| `publish-github-release` | Publish or update a GitHub Release for the current repository. | common, packaging, release |
| `update-dependencies` | Update project dependencies with uv. | common, packaging |
| `build-package` | Build the package (wheel and sdist). | build, common, packaging |
| `bump-version` | Bump the project version. | common, packaging |
| `changelog` | Print the changelog for the current version based on git history and git-cliff. | common, packaging, release |
| `release` | Run a full release flow for package and containers. | common, containers, packaging, release |

### Container images

| Task | Description | Tags |
| --- | --- | --- |
| `build-image` | Build the container image for this project using the Dockerfile template. | build, containers |
| `build-deps-image` | Build only the container dependency collector image for this project. | build, containers |
| `run-container` | Run the Docker image as a container for this project. By default, this will run the most-recently-built tag for the project's image. | containers |
| `push-image` | Push the Docker image for this project to the container registry. | containers, packaging, release |
| `build` | Build the project and its containers. | common, containers, packaging |
| `container-shell` | Run the debug image with an interactive shell. | containers, debug |

### Development stacks

| Task | Description | Tags |
| --- | --- | --- |
| `stack-up` | Bring up the development stack for the application. | containers, fastapi, web |
| `stack-down` | Bring down the development stack for the application. | containers, fastapi, web |
| `reset-db` | Reset the database by deleting the database volume. | containers, database, fastapi, web |
| `run-db-migrations` | Run database migrations. | containers, database, fastapi, web |
| `db-shell` | Open a psql shell to the database container. | containers, database, fastapi, web |

<!-- end-tasks-table -->

## Configuration and requirements

### Requirements

Every project needs a `pyproject.toml` file at its root and Poe the Poet available in its development environment.

Tasks that install, build, publish, or update dependencies require uv. Package and release tasks need a resolvable project version from `project.version` or Git tags. Dynamic versioning is supported but is not a baseline requirement.

### Task selection

Calling `tasks()` without arguments exposes the default `common` task set.

```toml
[tool.poe]
include_script = "common_python_tasks:tasks()"
```

Select optional task groups with tags when your project needs them.

```toml
[tool.poe]
include_script = "common_python_tasks:tasks(include_tags=['common', 'containers'])"
```

The `containers` tag also includes container-based development-stack tasks. Use the tags in the task tables to tailor a smaller task set.

### Package management

Packaging-related tasks, including `build-package`, `publish-package`, dependency updates, release version resolution, and container build metadata, use uv exclusively. The `uv` executable must be available on `PATH`.

### Publish target selection

The `publish-package` task resolves publish targets with this precedence.

1. Explicit task arguments (`repository` or `repository_url`)
2. Environment-variable fallback
3. uv project configuration fallback from `[[tool.uv.index]]`
4. The `uv publish` default

uv prefers named publish indexes.

- `COMMON_PYTHON_TASKS_PUBLISH_REPOSITORY`
- `UV_PUBLISH_INDEX`
- `COMMON_PYTHON_TASKS_PUBLISH_URL`
- `UV_PUBLISH_URL`

When using uv project configuration fallback, `[[tool.uv.index]]` must include both `name` and `publish-url` for publish selection. If multiple publishable indexes exist, set exactly one `default = true` or pass an explicit repository.

### Configuration precedence

For pytest and coverage, configuration resolves in the following order.

1. Matching `pyproject.toml` sections such as `[tool.pytest.ini_options]` and `[tool.coverage]`
2. Environment variables that specify a configuration path
3. Local configuration files in the project root
4. Bundled defaults from [`src/common_python_tasks/data`](src/common_python_tasks/data)

Ruff uses `RUFF_CONFIG` when set. Otherwise it discovers `.ruff.toml`, `ruff.toml`, or a `[tool.ruff]` section in `pyproject.toml`. When no project configuration is available, the tasks use the bundled Ruff defaults. Ruff configuration follows Ruff's native file precedence, so `.ruff.toml` takes precedence over `ruff.toml`, which takes precedence over `pyproject.toml` in the same directory.

The `format` task first applies safe fixes for unused imports and import sorting, then runs the Ruff formatter. The `lint` task checks both Ruff lint rules and formatting without changing files.

### Configuration examples

After installing the package, a minimal project configuration looks like this.

```toml
[project]
name = "simple-cli-tool"
version = "0.10.0"

[tool.poe]
include_script = "common_python_tasks:tasks()"
```

A container-based project can select the container task group and set its image details.

```toml
[tool.poe]
include_script = "common_python_tasks:tasks(include_tags=['common', 'containers'])"

[tool.poe.env]
CONTAINER_REGISTRY_USERNAME = "myusername"
PACKAGE_NAME = "containerized-app"
```

The `test` task automatically uses pytest configuration in `pyproject.toml`.

```toml
[tool.pytest.ini_options]
testpaths = ["tests", "integration"]
addopts = "-ra"
```

### Environment variables

#### Task configuration files

- `PYTEST_CONFIG`: Path to the pytest configuration file
- `COVERAGE_RCFILE`: Path to the coverage configuration file
- `RUFF_CONFIG`: Path to a Ruff TOML configuration file

#### Project and package settings

- `PACKAGE_NAME`: Overrides the package name inferred from `pyproject.toml`
- `COMMON_PYTHON_TASKS_PUBLISH_REPOSITORY`: Preferred publish repository/index name for `publish-package`
- `COMMON_PYTHON_TASKS_PUBLISH_URL`: Preferred uv publish upload URL for `publish-package` when no repository/index is selected
- `UV_PUBLISH_INDEX`: uv publish-index fallback for `publish-package`
- `UV_PUBLISH_URL`: uv publish upload-url fallback for `publish-package`

#### Container image settings

- `CONTAINER_REGISTRY_USERNAME`: Container-registry username for image tagging; the default is the current local user
- `CONTAINER_REGISTRY_URL`: Registry URL with a default of `docker.io/{username}`
- `CONTAINER_PYTHON_VARIANT`: Python base-image variant such as `slim`, `alpine`, etc. See <https://hub.docker.com/_/python> for available options. Defaults to `slim`; set to empty string for no variant (e.g., `FROM python:3.11`). The value is passed as the `PYTHON_VARIANT` Docker build argument and recorded in the `org.opencontainers.image.python.variant` image label.
- `CONTAINER_DOCKER_BUILD_ARGS`: Additional arguments passed directly to `docker build`, parsed using shell quoting rules. Free arguments provided to the task after `--` take precedence.
- `CONTAINER_DOCKERFILE_HOOK_PATH`: Optional host path to an executable hook script that receives the generated Dockerfile path and can modify the file before `docker build` runs.
- `CONTAINER_APT_PACKAGES`: Space-delimited system packages installed in the generated image
- `CONTAINER_CUSTOM_ENTRYPOINT`: Custom container entrypoint script. The value must match a key in `[project].scripts`.
- `CONTAINER_DEPS_IMAGE`: Existing dependency image used when neither `CONTAINER_DEPS_CONTENT` nor `CONTAINER_DEPS_FILE` is configured
- `CONTAINER_EXTENSION_FILES`: Colon-delimited local extension Dockerfile paths. Escape literal colons as `\:` or quote the complete path.
- `CONTAINER_EXTENSIONS`: Colon-delimited extension-bundle names or parameterized values. Escape literal colons as `\:` or quote the complete value.
- `CONTAINER_ENV`: Colon-delimited `KEY=VALUE` declarations injected into the rendered Dockerfile's builder stage. Escape literal colons as `\:` or quote the complete value.
- `.containerenv`: A project-root file that can supply the same declarations. It is loaded before the `container_envfile` task argument, `CONTAINER_ENV`, and the `container_env` task argument.
- `CONTAINER_PRUNE_KEEP`: Image-pruning policy after builds. `-1` keeps all images, `0` keeps only the latest, and `N` keeps the latest plus `N` prior images.
- `CONTAINER_DEPS_CONTENT`: Inline Dockerfile instructions for a dependency image that installs artifacts into `/tmp/deps`
- `CONTAINER_DEPS_FILE`: One or more dependency-image Dockerfiles. It accepts colon-delimited paths with literal colons escaped as `\:` and is used only when `CONTAINER_DEPS_CONTENT` is unset.
- `CONTAINER_DEPS_MAPPINGS`: Space-delimited `name:/target/path` entries for copying items from `/tmp/deps`. It is used only when no dependency move script is set.
- `CONTAINER_DEPS_MOVE_SCRIPT`: Raw executable script to run after `/tmp/deps` is copied into the image
- `CONTAINER_DEPS_MOVE_SCRIPT_PATH`: Host path to a dependency move script. This takes precedence over `CONTAINER_DEPS_MOVE_SCRIPT`.
- `UV_INDEX_{name}_USERNAME` and `UV_INDEX_{name}_PASSWORD`: Private Python index credentials consumed by uv during the Docker build. When any of these are set, the task automatically passes them as BuildKit secrets (`--secret id=uv_index_{name}_username,env=...`) and renders matching `--mount=type=secret` directives in the builder stage so uv can authenticate without baking credentials into the image. Multiple indices are supported; replace `{name}` with the uppercase index name (hyphens as underscores). These can be set in `tool.poe.env` for CI/CD or in the local environment for development.

#### Release settings

- `GITHUB_RELEASE_ASSETS`: Colon-delimited file paths or glob patterns to attach to a GitHub Release. The default is `dist/*`; escape literal colons as `\:` or quote the complete path.
- `SKIP_GITHUB_RELEASE`: Truthy value that skips GitHub Release publication
- `GITHUB_TOKEN` or `GH_TOKEN`: GitHub authentication token for releases and assets
- `GITHUB_REPOSITORY`: Optional repository-slug override for GitHub Release publication
- `GITHUB_API_URL` and `GITHUB_SERVER_URL`: GitHub Enterprise API-host settings
- `GITHUB_RELEASE_TAG`: Optional release tag name
- `GITHUB_RELEASE_NAME`: Optional release title
- `GITHUB_RELEASE_BODY`: Optional release body
- `RELEASE_UPDATE_CHANGELOG`: Truthy value that prepends `git-cliff --unreleased --tag "$RELEASE_TAG"` output to `CHANGELOG.md` before the release tag is created. It is enabled by default.
- `RELEASE_PRE_SCRIPT`: Optional shell command to run before release steps
- `RELEASE_POST_SCRIPT`: Optional shell command to run after release completion
- Release hooks receive `RELEASE_SCRIPT_PHASE`, `RELEASE_TAG`, `RELEASE_VERSION`, `RELEASE_STAGE`, `RELEASE_COMPONENT`, and `RELEASE_DRY_RUN`.

#### Docker Compose settings

- `COMPOSE_TYPE`: Application-stack type, such as `fastapi`
- `COMPOSE_ADDONS`: Colon-delimited services to include, such as `db`
- `COMPOSE_FILE`: Override for all compose files with colon-delimited paths
- `COMPOSE_OVERLAY_FILES`: Additional compose files to merge with colon-delimited paths
- `API_PORT`: API server port with a default of `8080`
- `SECRET_KEY`: Application secret key generated automatically when unset
- `ENVIRONMENT`: Environment name with a default of `production`
- `DEBUG_PORT`: Python debugger port in debug mode with a default of `5678`
- `DB_PORT`: PostgreSQL port with a default of `5432`
- `DB_USER`: Database user with a default of the package name
- `DB_BASE`: Database name with a default of the package name
- `DB_PASS`: Database password generated automatically when unset
- `POSTGRES_VERSION`: PostgreSQL version with a default of `17`
- `ADMINER_PORT`: Adminer web UI port with a default of `8081`

#### Debugging

- `COMMON_PYTHON_TASKS_LOG_LEVEL`: Set to `DEBUG` to show detailed configuration resolution

## Containers and development stacks

Docker Compose development-stack tasks are available when the `containers` tag is selected. The current stack supports FastAPI applications and an optional PostgreSQL database.

### Native Docker build arguments

Arguments after the task's `--` separator are passed directly to `docker build`. Docker performs option validation, so any supported build option and its value can be used without a package-specific allowlist.

```shell
poe build-image --single-arch -- \
  --secret id=pip_conf,env=PIP_CONF \
  --ssh default \
  --add-host example:127.0.0.1
```

Set `CONTAINER_DOCKER_BUILD_ARGS` to provide the same arguments through the environment. The value uses shell quoting rules, and task arguments provided after `--` take precedence.

Settings that affect generated Dockerfile content or dependency-image orchestration can be persisted directly in the project configuration.

```toml
[tool.poe.env]
CONTAINER_APT_PACKAGES = "curl jq"
CONTAINER_CUSTOM_ENTRYPOINT = "serve"
CONTAINER_DEPS_IMAGE = "example/dependencies:latest"
```

### Stack configuration

Set `COMPOSE_TYPE` to select the application stack. `fastapi` is currently supported and includes optional database support and Alembic migrations.

```toml
[tool.poe.env]
COMPOSE_TYPE = "fastapi"
```

Set `COMPOSE_ADDONS` to select extra services. Addon names are colon-delimited, and `db` is the currently available addon.

```toml
[tool.poe.env]
COMPOSE_ADDONS = "db"
```

### Compose-file customization

The compose setup resolves files in this precedence order.

1. **Environment override** uses `COMPOSE_FILE` with colon-delimited paths.
2. **Automatically loaded files** are based on `COMPOSE_TYPE` and `COMPOSE_ADDONS`.
   - `compose-base.yml` provides the core application service.
   - `compose-{addon}.yml` adds one file per addon, such as `compose-db.yml`.
   - `compose-debug.yml` is used when the `--debug` flag is present.
   - `compose-{addon}-debug.yml` provides debug overlays for addons.
3. **Additional overlays** use `COMPOSE_OVERLAY_FILES` with colon-delimited paths.

You can provide local compose files or allow the tasks to use bundled templates.

### FastAPI stack

The FastAPI stack uses the standard Dockerfile supplied by this package. Configure its ports, credentials, and database settings through the [Docker Compose settings](#docker-compose-settings) reference.

## Troubleshooting

### Tasks not showing up with `poe --help`

Check the `[tool.poe]` configuration in `pyproject.toml` and use `include_script`.

```toml
# Correct
[tool.poe]
include_script = "common_python_tasks:tasks(exclude_tags=['internal'])"

# Incorrect
[tool.poe]
includes = "common_python_tasks:tasks"
```

### Config files not being used

Review the [configuration precedence](#configuration-precedence) and enable debug logging to see the selected configuration.

```shell
COMMON_PYTHON_TASKS_LOG_LEVEL=DEBUG poe test
```

### GitHub Release assets not uploading

Confirm that `dist/` contains the built wheels and source distributions. You can override the default asset selection with `GITHUB_RELEASE_ASSETS`.

```shell
GITHUB_RELEASE_ASSETS="dist/*.whl:dist/*.tar.gz" poe publish-github-release
```

### Container build fails with "unable to find package"

Check that `pyproject.toml` has a correct package name and the package-discovery settings required by its build backend. For a `src` layout built with Hatch, configure `[tool.hatch.build.targets.wheel] packages = ["src/your_package"]`.

### Stack fails to start or services cannot connect

Check the following conditions.

- `COMPOSE_TYPE` is set and the required addon is selected.
- Default ports are available, including `8080` for the API, `5432` for PostgreSQL, and `8081` for Adminer.
- The Docker daemon is running, as verified with `docker info`.
- Service logs are available through `docker compose logs` in the project directory.

### Database migrations fail

Verify that the `db` addon is selected, Alembic is configured at the expected location, and its credentials match the generated `.env` values. Use `poe db-shell` to inspect the database manually.

### Secrets are not generated

Ensure the project-root `.env` file is writable and inspect its permissions with `ls -la .env`. You can also generate a value manually with `python -c "import secrets; print(secrets.token_hex(32))"`.

## Design choices

### Dockerfile design

See the [standard Dockerfile template](src/common_python_tasks/data/generic/Dockerfile.j2) for the implementation.

- Multi-stage build: The build stage installs uv and builds a wheel. The runtime stage installs only the wheel to keep the final image slim and reproducible.
- Cache mounts: Pip and uv cache mounts speed up iterative builds without bloating the final image.
- Explicit build metadata: `PYTHON_VERSION`, `UV_VERSION`, `PACKAGE_VERSION`, `PACKAGE_NAME`, `AUTHORS`, and `GIT_COMMIT` make image metadata predictable and auditable.
- Project-level build settings: `CONTAINER_APT_PACKAGES`, `CONTAINER_CUSTOM_ENTRYPOINT`, and `CONTAINER_DEPS_IMAGE` configure generated image behavior without being encoded as generic Docker arguments.
- Optional debug stage: The image exports and installs the `debug` dependency group only when present and does not include it in the default final image.
- Stable package path: Symlinks give entrypoints and consumers consistent `/pkg` and `/_$PACKAGE_NAME` paths regardless of wheel layout.
- Safe entrypoint selection: The default entrypoint resolves the console script matching the package name and falls back to `python`. `CONTAINER_CUSTOM_ENTRYPOINT` is validated against `[project].scripts`.
- Minimal final image: The standard slim Python base, cache cleanup, and explicit `runtime` final target keep the default image small.

## Project notes

- This project dogfoods itself. Set `PYTHONPATH=src` when running its tasks locally so Poe uses the local package rather than the installed version.
- `RELEASE_UPDATE_CHANGELOG` is enabled by default and prepends the generated changelog section before the release tag is created. Set it to a falsy value to manage changelog commits yourself.
- `RELEASE_PRE_SCRIPT` and `RELEASE_POST_SCRIPT` are advanced hooks for release-specific work, such as updating a version reference in another file.
- The project is in alpha status, so breaking changes may occur between minor versions before 1.0.0.

## Contributing

Contributions and feedback are welcome. Please open an issue or discussion to talk through a change before submitting a pull request.
