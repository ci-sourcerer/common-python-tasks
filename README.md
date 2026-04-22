# Common Python Tasks

This package is a collection of (very) opinionated [Poe the Poet](https://poethepoet.natn.io/guides/packaged_tasks.html) Python tasks for common Python development workflows.

Instead of writing your own tasks for formatting, linting, testing, packaging, and more, you can use these pre-built tasks that work out of the box with reasonable defaults and support configuration overrides when needed. In the past, I found myself copying and pasting the same task definitions across projects, and this package is my attempt to DRY up that workflow and provide a single source of truth for common Python development tasks. I hope you can use them too.

## Quick start

### Automated setup

You can add `common-python-tasks` to a new project by using the handy automated installation script.

```shell
curl -sSL https://api.github.com/repos/ci-sourcerer/common-python-tasks/contents/scripts/add-common-python-tasks.sh | jq -r '.content' | base64 -d | TAGS_TO_INCLUDE="format lint test" sh
```

This will complete the following steps.

1. Add the latest version of `common-python-tasks` to your `pyproject.toml` dependencies
2. Configure Poe the Poet to include only the tasks with the specified tags
3. Install the package using Poetry

**Always review scripts before running them!** Even though I believe I write good software, it's best practice to verify any script you download from the Internet.

### Manual setup

There's no real reason to run the automated script; I just like automating everything. You can achieve the same result by following these steps.

1. Add `common-python-tasks` to your `pyproject.toml` and configure Poe the Poet to include the desired tasks

    ```toml
    [project]
    name = "my-awesome-project"
    version = "0.0.3"
    dependencies = [
        "common-python-tasks==0.0.3",  # Always pin to a specific version
    ]

    [tool.poe]
    include_script = "common_python_tasks:tasks(include_tags=['format', 'lint', 'test'])"  # Include or exclude tasks by tags
    ```

2. Install the package

    ```shell
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
| `build` | Build the project and its containers (when `containers` tag is included) | packaging, containers |
| `build-image` | Build the container image for this project using the Dockerfile template (and configured extensions) | containers, build |
| `build-package` | Build the package (wheel and sdist) | packaging, build |
| `bump-version` | Bump the project version, defaulting to an inferred semantic bump from git history | packaging |
| `changelog` | Print the changelog for the current version based on git history | packaging, release |
| `clean` | Clean up temporary files and directories | clean |
| `container-shell` | Run the debug image with an interactive shell | containers, debug |
| `db-shell` | Open a psql shell to the database container | web, containers, database |
| `format` | Format code with autoflake, black, and isort | format |
| `lint` | Lint Python code with autoflake, black, isort, and flake8 | lint |
| `publish-package` | Publish the package to the PyPI server | packaging |
| `publish-github-release` | Publish or update a GitHub Release and attach built distribution assets | packaging, release |
| `push-image` | Push the Docker image to the container registry | containers, packaging, release |
| `release` | Run package release flow and publish containers when `containers` tag is included. Supports optional `RELEASE_PRE_SCRIPT` and `RELEASE_POST_SCRIPT` hooks. | packaging, release |
| `reset-db` | Reset the database by deleting the database volume | web, containers, database |
| `run-container` | Run the Docker image as a container | containers |
| `run-db-migrations` | Run database migrations | web, containers, database |
| `stack-down` | Bring down the development stack for the application | web, containers |
| `stack-up` | Bring up the development stack for the application | web, containers |
| `test` | Run the test suite with coverage | test |
<!-- end-tasks-table -->

## Docker Compose Development Stacks

Some tasks of certain tags provide Docker Compose-based development stacks for running your application with supporting services (databases, caches, etc.). Currently supports FastAPI applications with PostgreSQL.

### Configuration

#### `COMPOSE_TYPE`

Specifies the type of application stack. Currently supported:

- `fastapi` - FastAPI application with optional database, Alembic migrations

Set via environment variable:

```toml
[tool.poe.env]
COMPOSE_TYPE = "fastapi"
```

#### `COMPOSE_ADDONS`

Colon-separated list of additional services to include. Available addons:

- `db` - PostgreSQL database with Alembic migration support and Adminer web UI

Example:

```toml
[tool.poe.env]
COMPOSE_ADDONS = "db"
```

For multiple addons (future): `COMPOSE_ADDONS = "db:redis:cache"`

### Compose File Customization

The compose setup follows this precedence.

1. **Environment override** - `COMPOSE_FILE` environment variable with colon-separated paths
2. **Auto-loaded files** - Based on `COMPOSE_TYPE` and `COMPOSE_ADDONS`:
   - `compose-base.yml` - Core application service
   - `compose-{addon}.yml` - For each addon (e.g., `compose-db.yml`)
   - `compose-debug.yml` - When `--debug` flag is used
   - `compose-{addon}-debug.yml` - Debug overlays for addons
3. **Additional overlays** - `COMPOSE_OVERLAY_FILES` with colon-separated paths

You can provide local compose files or let the tasks use bundled templates.

### `fastapi`

The `fastapi` stack includes a service for your FastAPI application. It uses the standard Dockerfile included with this package.

#### Environment variables

- `API_PORT` - Port for the API server (default: `8080`)
- `SECRET_KEY` - Application secret key (auto-generated and stored in `.env` if not set)
- `ENVIRONMENT` - Environment name like `development` or `production` (default: `production`)
- `DEBUG_PORT` - Port for the Python debugger when using `--debug` (default: `5678`)
- `DB_PORT` - PostgreSQL port (default: `5432`)
- `DB_USER` - Database user (default: package name)
- `DB_BASE` - Database name (default: package name)
- `DB_PASS` - Database password (auto-generated and stored in `.env` if not set)
- `POSTGRES_VERSION` - PostgreSQL Docker image version (default: `17`)
- `ADMINER_PORT` - Adminer web UI port (default: `8081`)

## How it works

### Prerequisites

Your project must meet the following requirements.

- Use Poetry for dependency management
- Have a `pyproject.toml` file at the root
- Have a package name (automatically inferred from `project.name` in `pyproject.toml` or set via `PACKAGE_NAME` environment variable)

### Configuration precedence

Tasks that need configuration files (`pytest`, `coverage`, `flake8`, `isort`) follow this order of precedence.

1. **`pyproject.toml` sections** - `[tool.pytest]`, `[tool.coverage]`, `[tool.isort]` take priority
2. **Environment variables** - Override config paths (see [Environment Variables](#environment-variables))
3. **Local config files** - `pytest.ini`, `.coveragerc`, `.flake8`, `.isort.cfg` in project root
4. **Bundled defaults** - Sensible defaults included with this package, found in the [`src/common_python_tasks/data`](src/common_python_tasks/data) directory

You can start with zero configuration and customize as needed.

### Environment variables

#### Configuration files

The following environment variables configure the paths to configuration files.

- `PYTEST_CONFIG` specifies the path to the pytest configuration file
- `COVERAGE_RCFILE` specifies the path to the coverage configuration file  
- `FLAKE8_CONFIG` specifies the path to the flake8 configuration file
- `ISORT_CONFIG` specifies the path to the isort configuration file

#### Package/Container settings

The following environment variables configure package and container behavior.

- `PACKAGE_NAME` overrides the package name (default is from `pyproject.toml`)
- `POETRY_VERSION` overrides the Poetry version for container builds
- `DOCKERHUB_USERNAME` specifies the Docker Hub username for image tagging (default is current local user)
- `CONTAINER_REGISTRY_URL` specifies the registry URL (default is `docker.io/{username}`)
- `CONTAINER_BUILD_ARGS` provides additional Docker build arguments in `KEY=VALUE:OTHER=VALUE` format
- `CONTAINER_EXTENSION_FILES` specifies colon-delimited local extension Dockerfile paths to include in the rendered build.
- `CONTAINER_EXTENSIONS` specifies colon-delimited extension bundle names or parameterized bundle values to include in the rendered build.
- `CONTAINER_ENV` provides colon-delimited `KEY=VALUE` declarations to inject into the builder stage of the rendered Dockerfile.
- `.containerenv` can also supply the same declarations from a file in the project root. It is the fallback source when neither `container_envfile` nor `CONTAINER_ENV` is provided.
- `CONTAINER_PRUNE_KEEP` controls image pruning after builds (`-1` keep all, `0` keep latest only, `N` keep latest + `N` previous)
- `CUSTOM_IMAGE_ENTRYPOINT` specifies a custom entrypoint script name for containers
- `CONTAINER_DEPS_CONTENT` supplies inline Dockerfile instructions for a dependency image that installs artifacts into `/tmp/deps`
- `CONTAINER_DEPS_FILE` points to one or more explicit Dockerfiles to build the dependency image. It may be a colon-delimited list of file paths and is used only when `CONTAINER_DEPS_CONTENT` is unset.
- `CONTAINER_DEPS_MAPPINGS` maps copied dependency names from `/tmp/deps` into destination paths, as whitespace-separated `name:/target/path` entries. This is only used when `CONTAINER_DEPS_MOVE_SCRIPT` or `CONTAINER_DEPS_MOVE_SCRIPT_PATH` is not set.
- `CONTAINER_DEPS_MOVE_SCRIPT` supplies a raw executable script to run after `/tmp/deps` is copied into the image. The script is written to `/tmp/container-deps-move-script` and executed with its own shebang.
- `CONTAINER_DEPS_MOVE_SCRIPT_PATH` supplies a host path to a script file to run after `/tmp/deps` is copied into the image. This path takes precedence over `CONTAINER_DEPS_MOVE_SCRIPT` when both are set.
- `GITHUB_RELEASE_ASSETS` colon-separated list of file paths or glob patterns to attach to the GitHub Release (default: `dist/*`)
- `SKIP_GITHUB_RELEASE` truthy value to skip GitHub Release publication.
- `GITHUB_TOKEN` or `GH_TOKEN` GitHub authentication token used to publish releases and upload assets.
- `GITHUB_REPOSITORY` optional override for the repository slug used when publishing a GitHub Release.
- `GITHUB_API_URL` and `GITHUB_SERVER_URL` configure the GitHub API host for GitHub Enterprise environments.
- `GITHUB_RELEASE_TAG` optional tag name to publish for the GitHub Release.
- `GITHUB_RELEASE_NAME` optional release title to use for the GitHub Release.
- `GITHUB_RELEASE_BODY` optional release body text to use for the GitHub Release.
- `RELEASE_PRE_SCRIPT` optional shell command to run before the release steps.
- `RELEASE_POST_SCRIPT` optional shell command to run after the release completes.
- Hook commands receive the following env vars: `RELEASE_TAG`, `RELEASE_VERSION`, `RELEASE_STAGE`, `RELEASE_COMPONENT`, and `RELEASE_DRY_RUN`.

#### Docker Compose settings

The following environment variables configure Docker Compose stacks (when using the `web` tag).

- `COMPOSE_TYPE` specifies the type of application stack (e.g., `fastapi`)
- `COMPOSE_ADDONS` colon-separated list of services to include (e.g., `db` for database)
- `COMPOSE_FILE` overrides all compose files with colon-separated paths
- `COMPOSE_OVERLAY_FILES` additional compose files to merge (colon-separated paths)
- `API_PORT` port for the API server (default: `8080`)
- `SECRET_KEY` application secret key (auto-generated if not set)
- `ENVIRONMENT` environment name (default: `production`)
- `DEBUG_PORT` port for Python debugger in debug mode (default: `5678`)
- `DB_PORT` PostgreSQL port (default: `5432`)
- `DB_USER` database user (default: package name)
- `DB_BASE` database name (default: package name)
- `DB_PASS` database password (auto-generated if not set)
- `POSTGRES_VERSION` PostgreSQL version (default: `17`)
- `ADMINER_PORT` Adminer web UI port (default: `8081`)

#### Debugging

The following environment variable enables debugging output.

- `COMMON_PYTHON_TASKS_LOG_LEVEL` should be set to `DEBUG` to see detailed configuration resolution

### Usage examples

You can include or exclude tasks by tags in your `pyproject.toml`

#### Minimal setup

```toml
[project]
name = "simple-cli-tool"
version = "0.0.3"
dependencies = ["common-python-tasks==0.0.3"]

[tool.poe]
include_script = "common_python_tasks:tasks(include_tags=['format', 'lint'])"
```

Available tasks: `format`, `lint`.

#### Container-based project

```toml
[project]
name = "containerized-app"
version = "0.0.3"
dependencies = ["common-python-tasks==0.0.3"]

[tool.poe]
include_script = "common_python_tasks:tasks(include_tags=['format', 'lint', 'test', 'containers'])"

[tool.poe.env]
DOCKERHUB_USERNAME = "myusername"
PACKAGE_NAME = "containerized-app"
```

Available tasks: All tasks including `build-image` and `push-image`.

#### Custom pytest configuration

```toml
[project]
name = "custom-test-setup"
dependencies = ["common-python-tasks==0.0.3"]
dynamic = ["version"]

[tool.poe]
include_script = "common_python_tasks:tasks(include_tags=['test'])"

[tool.pytest.ini_options]
testpaths = ["tests", "integration"]
addopts = "-ra"
```

The `test` task will automatically use your `[tool.pytest.ini_options]` configuration.

## Troubleshooting

### Tasks not showing up with `poe --help`

Check your `[tool.poe]` configuration in `pyproject.toml`. Make sure you're using `include_script`, not `includes`.

```toml
# Correct
[tool.poe]
include_script = "common_python_tasks:tasks(exclude_tags=['internal'])"

# Incorrect
[tool.poe]
includes = "common_python_tasks:tasks"
```

### Version bump fails with "no changes since last tag"

This is expected behavior. The `bump-version` task requires commits between the last tag and HEAD. You can resolve this in one of the following ways.

- Make changes and commit them first
- Delete the old tag (for example, `git tag -d v0.0.1`). This is not recommended. Versions should be immutable, and if you need to fix something, you should create a new patch version instead. Rarely do you want to pass off new code as an old version

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
- A package location defined with this configuration: `[tool.poetry] packages = [{ include = "your_package", from = "src" }]`

### Stack fails to start or services won't connect

If `stack-up` builds successfully but services can't connect:

- Check that required environment variables are set (`COMPOSE_TYPE` at minimum)
- Verify ports aren't already in use (defaults: 8080 for API, 5432 for database, 8081 for Adminer)
- Check Docker daemon is running: `docker info`
- View service logs: `docker-compose logs` in your project directory

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

### Dockerfile (see [src/common_python_tasks/data/Dockerfile](src/common_python_tasks/data/Dockerfile))

The standard Python Dockerfile incorporates several intentional design choices.

- Multi-stage build: The build stage installs Poetry and builds a wheel while the runtime stage installs only the wheel to keep the final image slim and reproducible
- Pip and Poetry cache mounts speed up iterative builds without bloating the final image
- Explicit inputs through build args (`PYTHON_VERSION`, `POETRY_VERSION`, `PACKAGE_NAME`, `AUTHORS`, `GIT_COMMIT`, `CUSTOM_ENTRYPOINT`) make image metadata and behavior predictable and auditable
- Optional debug stage exports and installs the `debug` dependency group only when present without failing otherwise and is not part of the default final image
- Stable package path creates symlinks to the installed package so entrypoints and consumers have a consistent `/pkg` and `/_$PACKAGE_NAME` path regardless of wheel layout, which ensures that the package can be reliably imported and executed from a known location, and allows for the less common use case of reading files directly from the package path
- Safe entrypoint selection means the default entrypoint resolves the console script matching the package name while `CUSTOM_ENTRYPOINT` allows overriding at build time while keeping runtime behavior predictable
- Minimal final image uses the slim Python base by default, cleans wheel artifacts and caches, and sets `runtime` as the explicit final target so the debug stage is opt-in

## Notes

- This project dogfoods itself - it uses `common-python-tasks` for its own development
- `RELEASE_PRE_SCRIPT` and `RELEASE_POST_SCRIPT` hooks may not be necessary for most users, as this package promotes the use of `poetry-dynamic-versioning` and `git-cliff` to automate versioning and changelog generation based on git history. However, one advanced use case for the `RELEASE_PRE_SCRIPT` hook is to edit a file before release, such as a README that references the current stable version number. This allows you to keep the README up to date with the latest version without hardcoding it.
- Contributions welcome! Open an issue/discussion to discuss changes before submitting a PR. I do not claim to have all the answers, and you can help determine the future of low-code solutions for Python. I am very interested in your feedback as I don't want to work in a vacuum
- Alpha status: Expect breaking changes between minor versions until 1.0.0
