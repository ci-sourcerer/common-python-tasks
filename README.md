# Common Python tasks

This package is a collection of (very) opinionated [Poe the Poet Python tasks](https://poethepoet.natn.io/guides/packaged_tasks.html) for common Python development workflows.

## Quick start

### Automated setup

You can add `common-python-tasks` to a new project by using the handy automated installation script.

```shell
curl -sSL https://api.github.com/repos/ci-sourcerer/common-python-tasks/contents/scripts/add-common-python-tasks.sh | TAGS_TO_INCLUDE="format lint test" sh
```

This will complete the following steps.

1. Add the latest version of `common-python-tasks` to your `pyproject.toml` dependencies
2. Configure Poe the Poet to include only the tasks with the specified tags
3. Install the package using Poetry

**Always review scripts before running them!** Even though I believe I write good software, it's best practice to verify any script you download from the Internet.

### Manual setup

1. Add `common-python-tasks` to your `pyproject.toml` and configure Poe the Poet to include the desired tasks

    ```toml
    [project]
    name = "my-awesome-project"
    version = "0.0.1"
    dependencies = [
        "common-python-tasks==0.0.1",  # Always pin to a specific version
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

| Task | Description | Tags |
| - | - | - |
| `build` | Build the project; also builds container images when the `containers` tag is included | packaging, containers |
| `build-image` | Build a container image using the bundled Containerfile template | containers, build |
| `build-package` | Build the package (wheel and sdist) | packaging, build |
| `bump-version` | Bump project version and create a git tag | packaging |
| `clean` | Remove build, cache, and coverage artifacts | clean |
| `format` | Format code with autoflake, black, and isort | format |
| `lint` | Run autoflake, black, isort checks, and flake8 linting | lint |
| `publish-package` | Publish the package to PyPI via Poetry | packaging |
| `push-image` | Push container images to the configured registry | containers, packaging, release |
| `run-container` | Run the built container image with the selected tag | containers |
| `test` | Run tests with pytest and generate coverage reports | test |

## How it works

### Prerequisites

Your project must meet the following requirements.

- Use Poetry for dependency management
- Have a `pyproject.toml` file at the root
- Have a package name (automatically inferred from `project.name` in `pyproject.toml`, or set via `PACKAGE_NAME` environment variable)

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
- `CUSTOM_IMAGE_ENTRYPOINT` specifies a custom entrypoint script name for containers

#### Debugging

The following environment variable enables debugging output.

- `COMMON_PYTHON_TASKS_LOG_LEVEL` should be set to `DEBUG` to see detailed configuration resolution

### Usage examples

You can include or exclude tasks by tags in your `pyproject.toml`

#### Minimal setup

```toml
[project]
name = "simple-cli-tool"
version = "0.0.1"
dependencies = ["common-python-tasks==0.0.1"]

[tool.poe]
include_script = "common_python_tasks:tasks(include_tags=['format', 'lint'])"
```

Available tasks: `format`, `lint`.

#### Container-based project

```toml
[project]
name = "containerized-app"
version = "0.0.1"
dependencies = ["common-python-tasks==0.0.1"]

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
dependencies = ["common-python-tasks==0.0.1"]
dynamic = ["version"]

[tool.poe]
include_script = "common_python_tasks:tasks(include_tags=['test'])"

[tool.pytest.ini_options]
testpaths = ["tests", "integration"]
addopts = "-ra"
```

The `test` task will automatically use your `[tool.pytest.ini_options]` configuration.

## Release workflow

The `release` tag is used to identify tasks that are part of the release process. To perform a complete release, follow these steps.

```shell
# 1. Ensure all changes are committed
git add .
git commit -m "Prepare for release"  # You probably want a better commit message than this

# 2. Bump the version (creates a git tag)
poe bump-version patch  # or 'minor', 'major'; for pre-releases: poe bump-version patch --stage alpha

# 3. Build the package
poetry build

# 4. Publish to PyPI
poe publish-package

# 5. (Optional) If using containers
poe build-image
poe push-image

# 6. Push tags to remote
git push --tags
```

## Troubleshooting

### "No tests were collected"

The `test` task exits with code 5 if no tests are found. You can address this in one of the following ways.

- Add tests to your `tests/` directory
- Exclude the `test` tag and simply do not run `poe test` with this configuration `include_script = "common_python_tasks:tasks(exclude_tags=['test', 'internal'])"`

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
- If you need to re-tag the same commit, delete the old tag (for example, `git tag -d v0.0.1`). This is not recommended. Versions should be immutable, and if you need to fix something, you should create a new patch version instead

### Config files not being used

Check the configuration precedence (see [How it works](#how-it-works)). Use debug logging to see which config is selected.

```shell
COMMON_PYTHON_TASKS_LOG_LEVEL=DEBUG poe test
```

### Container build fails with "unable to find package"

Make sure your `pyproject.toml` contains the following.

- A correct package name in `[project]`
- A package location defined with this configuration `[tool.poetry] packages = [{ include = "your_package", from = "src" }]`

## Design choices

### Containerfile (see [src/common_python_tasks/data/Containerfile](src/common_python_tasks/data/Containerfile))

The standard Python Containerfile incorporates several intentional design choices.

- Multi-stage build: the build stage installs Poetry and builds a wheel while the runtime stage installs only the wheel to keep the final image slim and reproducible
- Cache-aware installs mean pip and Poetry cache mounts speed up iterative builds without bloating the final image
- Explicit inputs through build args (`PYTHON_VERSION`, `POETRY_VERSION`, `PACKAGE_NAME`, `AUTHORS`, `GIT_COMMIT`, `CUSTOM_ENTRYPOINT`) make image metadata and behavior predictable and auditable
- Optional debug stage exports and installs the `debug` dependency group only when present without failing otherwise and is not part of the default final image
- Stable package path creates symlinks to the installed package so entrypoints and consumers have a consistent `/pkg` and `/_$PACKAGE_NAME` path regardless of wheel layout, which ensures that the package can be reliably imported and executed from a known location, and allows for the less common use case of reading files directly from the package path
- Safe entrypoint selection means the default entrypoint resolves the console script matching the package name while `CUSTOM_ENTRYPOINT` allows overriding at build time while keeping runtime behavior predictable
- Minimal final image uses the slim Python base, cleans wheel artifacts and caches, and sets `runtime` as the explicit final target so the debug stage is opt-in

## Notes

- This project dogfoods itself - it uses `common-python-tasks` for its own development
- Contributions welcome! Open an issue/discussion to discuss changes before submitting a PR. I do not claim to have all the answers, and you can help determine the future of low-code solutions for Python. I am very interested in your feedback as I don't want to work in a vacuum
- Alpha status: expect breaking changes between minor versions until 1.0.0
