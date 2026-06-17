# Common Python Tasks

This package is a collection of (very) opinionated [Poe the Poet](https://poethepoet.natn.io/guides/packaged_tasks.html) Python tasks for common Python development workflows.

Instead of writing your own tasks for formatting, linting, testing, packaging, and more, you can use these prebuilt tasks that work immediately with reasonable defaults and support configuration overrides when needed. In the past, I found myself copying and pasting the same task definitions across projects, and this package is my attempt to DRY up that workflow and provide a single source of truth for common Python development tasks. I hope you can use them too.

## Quick start

### Automated setup

You can add `common-python-tasks` to a new project by using the handy automated installation script.

```shell
curl -sSL https://api.github.com/repos/ci-sourcerer/common-python-tasks/contents/scripts/add-common-python-tasks.sh | jq -r '.content' | base64 -d | sh
```

To install a specific release, set the environment variable `COMMON_PYTHON_TASKS_VERSION`.

```shell
COMMON_PYTHON_TASKS_VERSION=0.4.1 \
  sh -c "$(curl -sSL https://api.github.com/repos/ci-sourcerer/common-python-tasks/contents/scripts/add-common-python-tasks.sh | jq -r '.content' | base64 -d)"
```

This will complete the following steps.

1. Add the latest version of `common-python-tasks` to your `pyproject.toml` dependencies
2. Configure Poe the Poet to expose the default common task set
3. Install dependencies for your project

**Always review scripts before running them!** Even though I believe I write good software, it's best practice to verify any script you download from the Internet.

### Manual setup

There's no real reason to run the automated script; I just like automating everything. You can achieve the same result by following these steps.

1. Add `common-python-tasks` to your `pyproject.toml` and configure Poe the Poet

    ```toml
    [project]
    dependencies = [
        "common-python-tasks==0.4.1"  # Always pin to a specific version
    ]

    [tool.poe]
    include_script = "common_python_tasks:tasks()"  # Uses the default `common` task set
    ```

2. Install the package

    ```shell
    uv sync
    # or, for Poetry workflows
    poetry install
    ```

3. Run tasks

    ```shell
    poe format  # Format your code
    poe lint    # Check code quality
    poe test    # Run tests with coverage
    ```

## Available tasks

Internal tasks are used by other tasks and are not meant to be run directly.

<!-- tasks-table -->
| Task | Description | Tags |
| - | - | - |
| `test` | Run the test suite with coverage (if `pytest-cov` is installed). | common, test |
| `clean` | Clean up temporary files and directories. | clean, common |
| `format` | Format Python code with autoflake, black, and isort. | common, format |
| `lint` | Lint Python code with autoflake, black, isort, and flake8. | common, lint |
| `build-image` | Build the container image for this project using the Dockerfile template. | build, containers |
| `build-deps-image` | Build only the container dependency collector image for this project. | build, containers |
| `run-container` | Run the Docker image as a container for this project. By default (when `tag` is `None`) this will run the most-recently-built tag for the project's image. | containers |
| `push-image` | Push the Docker image for this project to the container registry. | containers, packaging, release |
| `publish-package` | Publish the package to the PyPI server. | common, packaging |
| `publish-github-release` | Publish or update a GitHub Release for the current repository. | common, packaging, release |
| `build-package` | Build the package (wheel and sdist). | build, common, packaging |
| `bump-version` | Bump the project version. | common, packaging |
| `changelog` | Print the changelog for the current version based on git history and git-cliff. | common, packaging, release |
| `release` | Run a full release flow for package and containers. | common, containers, packaging, release |
| `build` | Build the project and its containers. | common, containers, packaging |
| `stack-up` | Bring up the development stack for the application. | containers, fastapi, web |
| `stack-down` | Bring down the development stack for the application. | containers, fastapi, web |
| `reset-db` | Reset the database by deleting the database volume. | containers, database, fastapi, web |
| `run-db-migrations` | Run database migrations. | containers, database, fastapi, web |
| `db-shell` | Open a psql shell to the database container. | containers, database, fastapi, web |
| `container-shell` | Run the debug image with an interactive shell. | containers, debug |
<!-- end-tasks-table -->

## Docker Compose Development Stacks

Some tasks of certain tags provide Docker Compose-based development stacks for running your application with supporting services (databases, caches, etc.). Currently supports FastAPI applications with PostgreSQL.

### Configuration

#### `COMPOSE_TYPE`

Specifies the type of application stack. Currently supported:

- `fastapi`: FastAPI application with optional database support and Alembic migrations

Set via environment variable:

```toml
[tool.poe.env]
COMPOSE_TYPE = "fastapi"
```

#### `COMPOSE_ADDONS`

Colon-separated list of additional services to include. Available addons:

- `db`: PostgreSQL database with Alembic migration support and Adminer web UI

Example:

```toml
[tool.poe.env]
COMPOSE_ADDONS = "db"
```

For multiple addons (future): `COMPOSE_ADDONS = "db:redis:cache"`

### Compose File Customization

The compose setup follows this precedence.

1. **Environment override**: `COMPOSE_FILE` environment variable with colon separated paths
2. **Automatically loaded files**: Based on `COMPOSE_TYPE` and `COMPOSE_ADDONS`
    - `compose-base.yml`: Core application service
    - `compose-{addon}.yml`: One file for each addon; for example, `compose-db.yml`
    - `compose-debug.yml`: Used when the `--debug` flag is present
    - `compose-{addon}-debug.yml`: Debug overlays for addons
3. **Additional overlays**: `COMPOSE_OVERLAY_FILES` with colon separated paths

You can provide local compose files or let the tasks use bundled templates.

### `fastapi`

The `fastapi` stack includes a service for your FastAPI application. It uses the standard Dockerfile included with this package.

#### Environment variables

- `API_PORT`: Port for the API server (default: `8080`)
- `SECRET_KEY`: Application secret key; generated automatically and stored in `.env` if not set
- `ENVIRONMENT`: Environment name such as `development` or `production` (default: `production`)
- `DEBUG_PORT`: Port for the Python debugger when using `--debug` (default: `5678`)
- `DB_PORT`: PostgreSQL port (default: `5432`)
- `DB_USER`: Database user (default: package name)
- `DB_BASE`: Database name (default: package name)
- `DB_PASS`: Database password; generated automatically and stored in `.env` if not set
- `POSTGRES_VERSION`: PostgreSQL Docker image version (default: `17`)
- `ADMINER_PORT`: Adminer web UI port (default: `8081`)

## How it works

### Prerequisites

Your project must meet the following requirements.

- Uses Poetry or uv for dependency management
- Uses Poe the Poet for task management
- Has `poetry-dynamic-versioning` or `uv-dynamic-versioning` as a dependency
- Has a `pyproject.toml` file at the root
- Has a package name (automatically inferred from `project.name` in `pyproject.toml` or set via `PACKAGE_NAME` environment variable)

### Package manager backend selection

Packaging-related tasks (`build-package`, `publish-package`, release tagging/version resolution, and related container build metadata) support both Poetry and uv.

Backend selection uses this precedence.

1. `COMMON_PYTHON_TASKS_PACKAGE_MANAGER`
2. `COMMON_PYTHON_TASKS_BUILD_TOOL`
3. `PACKAGE_MANAGER`
4. Auto-discovery (`auto`) based on installed tools and project metadata

Supported values are `poetry`, `uv`, and `auto`.

### Configuration precedence

Tasks that need configuration files (`pytest`, `coverage`, `flake8`, `isort`) follow this order of precedence.

1. **`pyproject.toml` sections**: `[tool.pytest]`, `[tool.coverage]`, `[tool.isort]` take priority
2. **Environment variables**: Override config paths; see [Environment Variables](#environment-variables)
3. **Local config files**: `pytest.ini`, `.coveragerc`, `.flake8`, `.isort.cfg` in the project root
4. **Bundled defaults**: Sensible defaults included with this package, found in the [`src/common_python_tasks/data`](src/common_python_tasks/data) directory

You can start with zero configuration and customize as needed.

### Environment variables

#### Configuration files

The following environment variables configure the paths to configuration files.

- `PYTEST_CONFIG`: Specifies the path to the pytest configuration file
- `COVERAGE_RCFILE`: Specifies the path to the coverage configuration file
- `FLAKE8_CONFIG`: Specifies the path to the flake8 configuration file
- `ISORT_CONFIG`: Specifies the path to the isort configuration file

#### Package/Container settings

The following environment variables configure package and container behavior.

- `PACKAGE_NAME`: Overrides the package name; the default comes from `pyproject.toml`
- `COMMON_PYTHON_TASKS_PACKAGE_MANAGER`: Selects package manager backend (`poetry`, `uv`, or `auto`)
- `COMMON_PYTHON_TASKS_BUILD_TOOL`: Alias for `COMMON_PYTHON_TASKS_PACKAGE_MANAGER`
- `PACKAGE_MANAGER`: Alias for `COMMON_PYTHON_TASKS_PACKAGE_MANAGER`
- `CONTAINER_REGISTRY_USERNAME`: Specifies the container registry username for image tagging; the default is the current local user
- `CONTAINER_REGISTRY_URL`: Specifies the registry URL (default: `docker.io/{username}`)
- `CONTAINER_BUILD_ARGS`: Provides additional Docker build arguments in `KEY=VALUE:OTHER=VALUE` format
- `CONTAINER_EXTENSION_FILES`: Specifies colon delimited local extension Dockerfile paths to include in the rendered build
- `CONTAINER_EXTENSIONS`: Specifies colon delimited extension bundle names or parameterized bundle values to include in the rendered build
- `CONTAINER_ENV`: Provides colon delimited `KEY=VALUE` declarations to inject into the builder stage of the rendered Dockerfile
- `.containerenv`: Can also supply the same declarations from a file in the project root. It is loaded first, then `container_envfile`, then `CONTAINER_ENV`, and finally `container_env`.
- `CONTAINER_PRUNE_KEEP`: Controls image pruning after builds (`-1` keeps all, `0` keeps the latest only, `N` keeps the latest plus `N` previous)
- `CUSTOM_ENTRYPOINT`: Specifies a custom entrypoint script name for containers. The value must match a key in `[project].scripts`; unknown values fail the build
- `CONTAINER_DEPS_CONTENT`: Supplies inline Dockerfile instructions for a dependency image that installs artifacts into `/tmp/deps`
- `CONTAINER_DEPS_FILE`: Points to one or more explicit Dockerfiles to build the dependency image. It may be a colon delimited list of file paths and is used only when `CONTAINER_DEPS_CONTENT` is unset
- `CONTAINER_DEPS_MAPPINGS`: Maps copied dependency names from `/tmp/deps` into destination paths as space separated `name:/target/path` entries. This is used only when `CONTAINER_DEPS_MOVE_SCRIPT` or `CONTAINER_DEPS_MOVE_SCRIPT_PATH` is not set
- `CONTAINER_DEPS_MOVE_SCRIPT`: Supplies a raw executable script to run after `/tmp/deps` is copied into the image. The script is written to `/tmp/container-deps-move-script` and executed with its own shebang
- `CONTAINER_DEPS_MOVE_SCRIPT_PATH`: Supplies a host path to a script file to run after `/tmp/deps` is copied into the image. This path takes precedence over `CONTAINER_DEPS_MOVE_SCRIPT` when both are set
- `GITHUB_RELEASE_ASSETS`: Colon separated list of file paths or glob patterns to attach to the GitHub Release (default: `dist/*`)
- `SKIP_GITHUB_RELEASE`: Truthy value to skip GitHub Release publication
- `GITHUB_TOKEN` or `GH_TOKEN`: GitHub authentication token used to publish releases and upload assets
- `GITHUB_REPOSITORY`: Optional override for the repository slug used when publishing a GitHub Release
- `GITHUB_API_URL` and `GITHUB_SERVER_URL`: Configure the GitHub API host for GitHub Enterprise environments
- `GITHUB_RELEASE_TAG`: Optional tag name to publish for the GitHub Release
- `GITHUB_RELEASE_NAME`: Optional release title to use for the GitHub Release
- `GITHUB_RELEASE_BODY`: Optional release body text to use for the GitHub Release
- `RELEASE_UPDATE_CHANGELOG`: Truthy value to update `CHANGELOG.md` by prepending the `git-cliff --unreleased --tag "$RELEASE_TAG"` output before the release tag is created. This is enabled by default; set it to a falsy value if you want to disable changelog commits during release
- `RELEASE_PRE_SCRIPT`: Optional shell command to run before the release steps
- `RELEASE_POST_SCRIPT`: Optional shell command to run after the release completes
- Hook commands: Receive the following env vars; `RELEASE_SCRIPT_PHASE`, `RELEASE_TAG`, `RELEASE_VERSION`, `RELEASE_STAGE`, `RELEASE_COMPONENT`, and `RELEASE_DRY_RUN`

#### Docker Compose settings

The following environment variables configure Docker Compose stacks (when using the `web` tag).

- `COMPOSE_TYPE`: Specifies the type of application stack; for example, `fastapi`
- `COMPOSE_ADDONS`: Colon separated list of services to include; for example, `db` for database support
- `COMPOSE_FILE`: Overrides all compose files with colon separated paths
- `COMPOSE_OVERLAY_FILES`: Additional compose files to merge; uses colon separated paths
- `API_PORT`: Port for the API server (default: `8080`)
- `SECRET_KEY`: Application secret key; generated automatically if not set
- `ENVIRONMENT`: Environment name (default: `production`)
- `DEBUG_PORT`: Port for the Python debugger in debug mode (default: `5678`)
- `DB_PORT`: PostgreSQL port (default: `5432`)
- `DB_USER`: Database user (default: package name)
- `DB_BASE`: Database name (default: package name)
- `DB_PASS`: Database password; generated automatically if not set
- `POSTGRES_VERSION`: PostgreSQL version (default: `17`)
- `ADMINER_PORT`: Adminer web UI port (default: `8081`)

#### Debugging

The following environment variable enables debugging output.

- `COMMON_PYTHON_TASKS_LOG_LEVEL`: Set this to `DEBUG` to see detailed configuration resolution

### Usage examples

By default, `tasks()` exposes the common task set. You can still include or exclude tags in your `pyproject.toml` when needed.

#### Minimal setup

```toml
[project]
name = "simple-cli-tool"
version = "0.4.1"
dependencies = ["common-python-tasks==0.4.1"]

[tool.poe]
include_script = "common_python_tasks:tasks()"
```

Available tasks: common defaults such as `format`, `lint`, `test`, and `build`.

#### Container-based project

```toml
[project]
dependencies = ["common-python-tasks==0.4.1"]

[tool.poe]
include_script = "common_python_tasks:tasks(include_tags=['common', 'containers'])"

[tool.poe.env]
CONTAINER_REGISTRY_USERNAME = "myusername"
PACKAGE_NAME = "containerized-app"
```

Available tasks: All tasks including `build-image` and `push-image`.

#### Custom pytest configuration

```toml
[project]
dependencies = ["common-python-tasks==0.4.1"]

[tool.poe]
include_script = "common_python_tasks:tasks()"

[tool.pytest.ini_options]
testpaths = ["tests", "integration"]
addopts = "-ra"
```

The `test` task will automatically use your `[tool.pytest.ini_options]` configuration.

## Troubleshooting

### Tasks not showing up with `poe --help`

Check your `[tool.poe]` configuration in `pyproject.toml`. Make sure you're using `include_script`.

```toml
# Correct
[tool.poe]
include_script = "common_python_tasks:tasks(exclude_tags=['internal'])"

# Incorrect
[tool.poe]
includes = "common_python_tasks:tasks"
```

### Config files not being used

Check the configuration precedence (see [How it works](#how-it-works)). Use debug logging to see which config is selected.

### GitHub Release assets not uploading

If your release task does not attach assets, confirm `dist/` contains the built wheels and sdists. You can override the default asset selection using `GITHUB_RELEASE_ASSETS`, for example:

```shell
GITHUB_RELEASE_ASSETS="dist/*.whl:dist/*.tar.gz" poe publish-github-release
```

```shell
COMMON_PYTHON_TASKS_LOG_LEVEL=DEBUG poe test
```

### Container build fails with "unable to find package"

Make sure your `pyproject.toml` contains the following.

- A correct package name in `[project]`
- Package discovery settings required by your chosen build backend (for Poetry projects, this is commonly `[tool.poetry] packages = [{ include = "your_package", from = "src" }]`)

### Stack fails to start or services won't connect

If `stack-up` builds successfully but services can't connect:

- Check that required environment variables are set (`COMPOSE_TYPE` at minimum)
- Verify ports aren't already in use (defaults: 8080 for API, 5432 for database, 8081 for Adminer)
- Check Docker daemon is running: `docker info`
- View service logs: `docker compose logs` in your project directory

### Database migrations fail

If `run-db-migrations` fails:

- Ensure the `db` addon is included: `COMPOSE_ADDONS=db`
- Check that your project has Alembic configured with migrations in the expected location
- Verify database credentials in `.env` match your Alembic configuration
- Manually inspect the database: `poe db-shell`

### Secrets not being generated

If `SECRET_KEY` or `DB_PASS` aren't auto-generated:

- Ensure `.env` file is writable in your project root
- Check file permissions: `ls -la .env`
- Generate manually: `python -c "import secrets; print(secrets.token_hex(32))"`

## Design choices

### Dockerfile (see [`src/common_python_tasks/data/generic/Dockerfile.j2`](src/common_python_tasks/data/generic/Dockerfile.j2))

The standard Python Dockerfile incorporates several intentional design choices.

- Multi-stage build: The build stage installs the selected package manager backend (Poetry or uv) and builds a wheel while the runtime stage installs only the wheel to keep the final image slim and reproducible
- Pip and package-manager cache mounts: Speed up iterative builds without bloating the final image
- Explicit inputs through build args: `PYTHON_VERSION`, `PACKAGE_MANAGER`, `PACKAGE_MANAGER_VERSION`, `PACKAGE_NAME`, `AUTHORS`, `GIT_COMMIT`, and `CUSTOM_ENTRYPOINT` make image metadata and behavior predictable and auditable
- Optional debug stage: Exports and installs the `debug` dependency group only when present, without failing otherwise, and is not part of the default final image
- Stable package path: Creates symlinks to the installed package so entrypoints and consumers have a consistent `/pkg` and `/_$PACKAGE_NAME` path regardless of wheel layout. This ensures that the package can be imported and executed from a known location and supports the less common case of reading files directly from the package path
- Safe entrypoint selection: The default entrypoint resolves the console script matching the package name and falls back to `python` when no matching script exists. `CUSTOM_ENTRYPOINT` allows an override at build time, and the override is validated strictly against `[project].scripts`
- Minimal final image: Uses the slim Python base by default, cleans wheel artifacts and caches, and sets `runtime` as the explicit final target so the debug stage remains optional

## Notes

- This project dogfoods itself; it uses `common-python-tasks` for its own development. **That said, you must set the environment variable `PYTHONPATH=src` when running tasks locally to ensure you are using the local version of the package instead of the installed version**
- `RELEASE_UPDATE_CHANGELOG` is enabled by default for releases and prepends a tagged section into `CHANGELOG.md` before the release tag is created. Set it to a falsy value if you prefer to manage changelog commits yourself.
- `RELEASE_PRE_SCRIPT` and `RELEASE_POST_SCRIPT` hooks may not be necessary for most users, as this package promotes dynamic versioning and `git-cliff` to automate versioning and changelog generation based on git history. One advanced use case for the `RELEASE_PRE_SCRIPT` hook is to edit another file before release, such as a README that references the current stable version number. This allows you to keep the README up to date with the latest version without hardcoding it.
- Contributions welcome! Open an issue/discussion to discuss changes before submitting a PR. I do not claim to have all the answers, and you can help determine the future of low-code solutions for Python. I am very interested in your feedback as I don't want to work in a vacuum
- Alpha status: Expect breaking changes between minor versions until 1.0.0
