import logging
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import subprocess
    from typing import Sequence, List, Tuple
    from typing_extensions import Literal

from poethepoet_tasks import TaskCollection


class _ColoredFormatter(logging.Formatter):
    """Custom formatter with color codes for different log levels."""

    COLORS = {
        "WARNING": "\033[93m",  # Yellow
        "ERROR": "\033[91m",  # Red
        "CRITICAL": "\033[91m",  # Red
        "RESET": "\033[0m",
    }

    def format(self, record: logging.LogRecord) -> str:
        log_color = self.COLORS.get(record.levelname, "")
        record.levelname = f"\033[1m{log_color}{record.levelname}{self.COLORS['RESET'] if log_color else ''}\033[0m"
        return super().format(record)


LOGGER = logging.getLogger("common_python_tasks")
handler = logging.StreamHandler()
handler.setFormatter(_ColoredFormatter("[%(asctime)s] %(levelname)s: %(message)s"))
LOGGER.addHandler(handler)
LOGGER.setLevel(
    {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }[os.getenv("COMMON_PYTHON_TASKS_LOG_LEVEL", "INFO").upper()]
)


def _get_authors() -> List[Tuple[str, str]]:
    import tomllib

    pyproject_data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    def _parse_author(author: dict[str, str]) -> tuple[str, str]:
        return (author.get("name") or "").strip(), (
            author.get("email") or ""
        ).strip().strip("<>")

    return [
        _parse_author(author)
        for author in (pyproject_data.get("project", {}).get("authors", []))
    ]


def _run_command(
    command: Sequence[str],
    *,
    capture_output: bool = False,
    acceptable_returncodes: Sequence[int] | None = None,
) -> "subprocess.CompletedProcess":
    import subprocess

    if acceptable_returncodes is None:
        acceptable_returncodes = {0}

    command_display = " ".join(command)
    LOGGER.debug("Running command: %s", command_display)
    out = subprocess.run(
        command,
        capture_output=capture_output,
        text=True,
    )
    if out.returncode not in acceptable_returncodes:
        if capture_output:
            stdout = out.stdout.strip() if out.stdout else ""
            stderr = out.stderr.strip() if out.stderr else ""
            details = ""
            if stdout:
                details += f"\nstdout: {stdout}"
            if stderr:
                details += f"\nstderr: {stderr}"
        else:
            details = ""
        LOGGER.error(
            "Command failed (exit code %d): %s%s",
            out.returncode,
            command_display,
            details,
        )
        sys.exit(out.returncode)
    return out


def _load_data_file(file_name: str) -> Tuple[str, str]:
    from importlib.resources import files

    try:
        data_files = files("common_python_tasks") / "data"
        data_file = data_files / file_name
        return (str(data_file), data_file.read_text())
    except (FileNotFoundError, TypeError) as e:
        LOGGER.error("Data file not found: %s (%s)", file_name, e)
        sys.exit(1)


def _get_dirty_files(ignore: list[str] = None) -> list[str]:
    if ignore is None:
        ignore = []

    return [
        f
        for f in [
            line[3:]
            for line in _run_command(
                ["git", "status", "--porcelain"], capture_output=True
            ).stdout.splitlines()
            if line
        ]
        if f not in ignore
    ]


def _get_version(files_to_ignore_as_dirty: list[str] = None) -> str:
    from dunamai import Style, Version

    if files_to_ignore_as_dirty is None:
        files_to_ignore_as_dirty = []

    dirty_files = _get_dirty_files(ignore=files_to_ignore_as_dirty)
    LOGGER.debug("Dirty files: %s", dirty_files)

    return Version.from_git().serialize(
        style=Style.Pep440,
        dirty=bool(dirty_files),
    )


def _get_image_tag(files_to_ignore_as_dirty: list[str] = None) -> str:
    if files_to_ignore_as_dirty is None:
        files_to_ignore_as_dirty = []

    return (
        _get_version(files_to_ignore_as_dirty=files_to_ignore_as_dirty)
        .replace(".post", "-post")
        .replace(".dev", "-dev")
        .replace("+", "-")
    )


def _has_tags_later_in_history() -> bool:
    result = _run_command(
        ["git", "tag"],
        capture_output=True,
        acceptable_returncodes={0, 128},
    )
    if result.returncode != 0 or not result.stdout.strip():
        # No tags exist
        return False

    # Check each tag to see if it's reachable from HEAD
    for tag in result.stdout.strip().split("\n"):
        # Check if HEAD is an ancestor of the tag's commit
        # If git merge-base --is-ancestor HEAD <tag> returns 0, then HEAD is an ancestor
        # If it returns 1, then HEAD is NOT an ancestor (tag is in a different branch/future)
        check_result = _run_command(
            ["git", "merge-base", "--is-ancestor", "HEAD", tag],
            capture_output=True,
            acceptable_returncodes={0, 1},
        )
        if check_result.returncode == 1:
            # HEAD is not an ancestor of this tag, meaning the tag is later in history
            return True

    return False


def _get_dockerhub_username() -> str:

    from getpass import getuser

    return os.getenv("DOCKERHUB_USERNAME") or getuser()


def _get_package_name(use_underscores: bool = False) -> str:
    import tomllib

    name = os.getenv("PACKAGE_NAME") or tomllib.loads(
        Path("pyproject.toml").read_text()
    ).get("project", {}).get("name")
    if use_underscores and name:
        name = name.replace("-", "_")
    return name


@lru_cache()
def _read_pyproject_toml() -> dict:
    """Read and cache the pyproject.toml file.

    Returns:
        Parsed pyproject.toml as a dictionary.
    """
    import tomllib

    return tomllib.loads(Path("pyproject.toml").read_text())


def get_config_path(
    env_var_name: str,
    local_config_filename: str,
    data_config_filename: str,
    *,
    tool_name: str | None = None,
) -> str | None:
    """Get the path to a configuration file.

    Checks for configuration in the following order:
    1. If tool_name provided, check if tool.{tool_name} exists in pyproject.toml
       - If it exists, return None (use pyproject.toml config)
    2. Check environment variable
    3. Check for local config file
    4. Fall back to bundled data file

    Args:
        env_var_name: Name of the environment variable to check
        local_config_filename: Name of the local config file to look for
        data_config_filename: Name of the bundled config file to use as fallback
        tool_name: Optional tool name to check in pyproject.toml under [tool.{tool_name}]

    Returns:
        Path to config file, or None if config exists in pyproject.toml
    """
    # Check if config exists in pyproject.toml
    if tool_name is not None:
        pyproject_data = _read_pyproject_toml()
        if pyproject_data.get("tool", {}).get(tool_name):
            LOGGER.debug("Using [tool.%s] configuration from pyproject.toml", tool_name)
            return None

    # Check environment variable
    if os.getenv(env_var_name):
        config_path = os.getenv(env_var_name)
        LOGGER.debug("Using config from %s: %s", env_var_name, config_path)
        return config_path

    # Check for local config file
    if Path(local_config_filename).exists():
        LOGGER.debug("Using local config file: %s", local_config_filename)
        return local_config_filename

    # Fall back to bundled data file
    config_path = _load_data_file(data_config_filename)[0]
    LOGGER.debug("Using bundled config file: %s", config_path)
    return config_path


tasks = TaskCollection(
    envfile=[
        f
        for f in [
            "project.properties",
            ".env",
        ]
        if Path(f).exists()
    ]
)

tasks.add(
    "_black",
    task_config={
        "cmd": "black --quiet .",
    },
    tags=[
        "common",
        "format",
        "internal",
    ],
)


@tasks.script(task_name="_isort", tags=["format", "internal"])
def isort() -> None:
    """Run isort formatting."""
    isort_config_path = get_config_path(
        "ISORT_CONFIG",
        ".isort.cfg",
        ".isort.cfg",
        tool_name="isort",
    )

    _run_command(
        [
            "isort",
            "--quiet",
            ".",
            "--settings-path",
        ]
        + ([isort_config_path] if isort_config_path else [])
    )


tasks.add(
    "_autoflake",
    task_config={
        "cmd": "autoflake --quiet --remove-all-unused-imports --recursive -i .",
    },
    tags=[
        "format",
        "internal",
    ],
)

tasks.add(
    "_black_check",
    task_config={"cmd": "black --quiet --diff . --check"},
    tags=[
        "lint",
        "internal",
    ],
)


@tasks.script(task_name="_isort_check", tags=["lint"])
def isort_check() -> None:
    """Run isort linting."""
    isort_config_path = get_config_path(
        "ISORT_CONFIG",
        ".isort.cfg",
        ".isort.cfg",
        tool_name="isort",
    )

    _run_command(
        [
            "isort",
            "--quiet",
            ".",
            "--check-only",
            "--settings-path",
        ]
        + ([isort_config_path] if isort_config_path else [])
    )


tasks.add(
    "_autoflake_check",
    task_config={
        "cmd": "autoflake --quiet --remove-all-unused-imports --recursive -cd ."
    },
    tags=[
        "lint",
        "internal",
    ],
)


@tasks.script(task_name="_flake8_check", tags=["lint"])
def flake8_check() -> None:
    """Run flake8 linting."""

    flake8_config_path = get_config_path(
        "FLAKE8_CONFIG",
        ".flake8",
        ".flake8",
    )

    _run_command(["flake8", ".", "--config", flake8_config_path])


@tasks.script(tags=["test"])
def test() -> None:
    """Run the test suite with coverage."""
    coverage_config_path = get_config_path(
        "COVERAGE_RCFILE",
        ".coveragerc",
        ".coveragerc",
        tool_name="coverage",
    )

    pytest_config_path = get_config_path(
        "PYTEST_CONFIG",
        "pytest.ini",
        "pytest.ini",
        tool_name="pytest",
    )

    exit_code = _run_command(
        (
            [
                "pytest",
                "-vv",
            ]
            + (
                [
                    "-c",
                    pytest_config_path,
                ]
                if pytest_config_path
                else []
            )
            + [
                "--cov=" + _get_package_name(use_underscores=True),
                "--cov-report=term-missing",
                "--cov-report=xml:coverage.xml",
            ]
            + (
                [
                    "--cov-config=" + coverage_config_path,
                ]
                if coverage_config_path
                else []
            )
        ),
        acceptable_returncodes={0, 5},
    ).returncode

    if exit_code == 5:
        LOGGER.warning("No tests were collected.")
        sys.exit(5)


tasks.add(
    "clean",
    task_config={
        "shell": "rm -rf .pytest_cache dist ./**/__pycache__ ./**/*.pyc .mypy_cache .coverage coverage.xml",
        "help": "Clean up temporary files and directories.",
    },
    tags=[
        "common",
        "clean",
    ],
)

tasks.add(
    "format",
    task_config={
        "sequence": ["_autoflake", "_black", "_isort"],
        "help": "Format Python code with autoflake8, black, and isort.",
    },
    tags=[
        "format",
    ],
)

tasks.add(
    "lint",
    task_config={
        "sequence": [
            "_autoflake_check",
            "_black_check",
            "_isort_check",
            "_flake8_check",
        ],
        "help": "Lint Python code with autoflake8, black, isort, and flake8.",
    },
    tags=[
        "lint",
    ],
)


def _build_image(
    containerfile_path: Path | None,
    containerfile_text: str | None,
    context_path: Path,
    debug: bool = False,
    python_version: str | None = None,
    no_cache: bool = False,
    plain: bool = False,
    all_archs: bool = False,
) -> None:
    import platform

    temp_file_path: str | None = None
    if containerfile_path is None:
        if containerfile_text is None:
            LOGGER.error(
                "Either containerfile_path or containerfile_text must be provided."
            )
            sys.exit(1)
        import tempfile

        tf = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            prefix="Containerfile.",
            suffix=".generated",
        )
        temp_file_path = tf.name
        with open(temp_file_path, "w", encoding="utf-8") as f:
            f.write(containerfile_text)
        containerfile_path = Path(temp_file_path)

    # Handle .dockerignore file
    dockerignore_path = context_path / ".dockerignore"
    temp_dockerignore_created = False
    if not dockerignore_path.exists():
        LOGGER.debug("No .dockerignore found, using built-in .dockerignore")
        builtin_dockerignore_content = _load_data_file(".dockerignore")[1]
        dockerignore_path.write_text(builtin_dockerignore_content, encoding="utf-8")
        temp_dockerignore_created = True

    delete_temp_file = False
    try:
        archs = ["linux/amd64", "linux/arm64"] if all_archs else None
        files_to_ignore = [".dockerignore"] if temp_dockerignore_created else []
        version_string = _get_image_tag(files_to_ignore_as_dirty=files_to_ignore)

        if debug:
            suffix = "-debug"
            target = "debug"
            tag = "debug"
        else:
            suffix = ""
            target = "runtime"
            # Only tag as 'latest' if there are no tags later in history
            tag = "latest" if not _has_tags_later_in_history() else None

        version_tag = f"{version_string}{suffix}"
        commit_tag = f"{_run_command(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True).stdout.strip()}{'-dirty' if _get_dirty_files(ignore=files_to_ignore) else ''}{suffix}"
        if python_version is None:
            python_version = platform.python_version()

        poetry_version = os.getenv("POETRY_VERSION")
        if poetry_version is None:
            poetry_version = (
                _run_command(["poetry", "--version"], capture_output=True)
                .stdout.strip()
                .split()[-1]
            )[0:-1]

        build_args = {
            k: v
            for k, v in {
                "PYTHON_VERSION": python_version,
                "POETRY_VERSION": poetry_version,
                "PACKAGE_NAME": _get_package_name(use_underscores=True),
                "AUTHORS": ",".join(
                    [f"{name} <{email}>" for name, email in _get_authors()]
                ),
                "GIT_COMMIT": commit_tag,
                "CUSTOM_ENTRYPOINT": os.getenv("CUSTOM_IMAGE_ENTRYPOINT"),
            }.items()
            if v is not None
        }
        tags_to_use = [t for t in (tag, version_tag, commit_tag) if t is not None]
        LOGGER.info("Building image with tags: %s", ", ".join(tags_to_use))
        build_cmd = (
            [
                "docker",
                "build",
                str(context_path),
                "-f",
                str(containerfile_path),
                "--target",
                target,
            ]
            + sum(
                [
                    ["--build-arg", f"{k}={v if v is not None else ''}"]
                    for k, v in build_args.items()
                ],
                [],
            )
            + (["--platform", ",".join(archs)] if archs else [])
            + (["--no-cache"] if no_cache else [])
            + sum(
                [["-t", f"{_get_package_name()}:{t}"] for t in tags_to_use],
                [],
            )
        )
        registry = os.environ.get(
            "CONTAINER_REGISTRY_URL",
            f"docker.io/{_get_dockerhub_username()}",
        ).strip()
        full_name = f"{registry}/{_get_package_name()}"
        for t in tags_to_use:
            build_cmd += ["-t", f"{full_name}:{t}"]

        if plain:
            build_cmd += ["--progress", "plain"]
        _run_command(build_cmd)
        delete_temp_file = True
    finally:
        if temp_file_path is not None and delete_temp_file:
            try:
                containerfile_path.unlink()
            except FileNotFoundError:
                pass
        if temp_dockerignore_created:
            try:
                dockerignore_path.unlink()
            except FileNotFoundError:
                pass


@tasks.script(tags=["containers", "build", "cli"])
def build_image(
    debug: bool = False,
    python_version: str | None = None,
    no_cache: bool = False,
    plain: bool = False,
    all_archs: bool = False,
) -> None:
    """Build the container image for this project using the Containerfile template.

    Args:
        debug: Build the debug image.
        python_version: Specify the Python version.
        no_cache: Do not use cache when building the image.
        plain: Do not pretty-print output.
        all_archs: Build images for all architectures.
    """

    _build_image(
        None,
        _load_data_file("Containerfile")[1],
        Path("."),
        debug=debug,
        python_version=python_version,
        no_cache=no_cache,
        plain=plain,
        all_archs=all_archs,
    )


@tasks.script(tags=["containers", "packaging", "release"])
def push_image(debug: bool = False) -> None:
    """Push the Docker image for this project to the container registry.

    Args:
        debug: Push the debug image.
    """

    if debug:
        suffix = "-debug"
        tag = "debug"
    else:
        suffix = ""
        # Only push 'latest' tag if there are no tags later in history
        tag = "latest" if not _has_tags_later_in_history() else None
    registry = os.environ.get(
        "CONTAINER_REGISTRY_URL",
        f"docker.io/{_get_dockerhub_username()}",
    ).strip()
    full_name = f"{registry}/{_get_package_name()}"
    tags_to_push = [t for t in [tag, f"{_get_image_tag()}{suffix}"] if t is not None]
    for t in tags_to_push:
        full_tag = f"{full_name}:{t}"
        LOGGER.info("Pushing image %s", full_tag)
        _run_command(["docker", "push", full_tag])


tasks.add(
    "publish-package",
    task_config={
        "cmd": "poetry publish",
        "help": "Publish the package to the PyPI server.",
    },
    tags=[
        "common",
        "packaging",
    ],
)


@tasks.script(tags=["common", "packaging"])
def bump_version(
    component: str = "patch",
    *,
    stage: str | None = None,
) -> None:
    """Bump the project version.

    Args:
        component: The version component to bump: "major", "minor", or "patch".".
        stage: Optional pre-release stage to apply: "alpha", "beta", or "rc".
    """
    from dunamai import Style, Version

    component = component.lower()
    stage = stage.lower() if stage is not None else None

    # Check if repository is dirty
    if _run_command(
        ["git", "status", "--porcelain"], capture_output=True
    ).stdout.strip():
        LOGGER.error(
            "Repository has uncommitted changes. Please commit or stash changes before bumping version."
        )
        sys.exit(1)

    # Try to get the latest tag; default to v0.0.0 if none exist
    last_tag_result = _run_command(
        ["git", "describe", "--tags", "--abbrev=0"],
        capture_output=True,
        acceptable_returncodes={0, 128},
    )
    last_tag = (
        last_tag_result.stdout.strip() if last_tag_result.returncode == 0 else "v0.0.0"
    )

    # Check if current version equals the last tag, refuse to bump if so
    current_version = _get_version()
    # Normalize last tag by stripping leading 'v' if present
    normalized_last_tag = last_tag[1:] if last_tag.startswith("v") else last_tag
    if current_version == normalized_last_tag and last_tag != "v0.0.0":
        LOGGER.error(
            "There have been no changes since the last version tag; cannot bump version as it would not change."
        )
        sys.exit(1)

    possible_components = ("major", "minor", "patch")
    if component not in possible_components:
        LOGGER.error(
            'Invalid component "%s". Must be one of: %s',
            component,
            ", ".join(possible_components),
        )
        sys.exit(1)
    component_index: "Literal[0, 1, 2]" = possible_components.index(component)

    prerelease_options = {
        "a": "alpha",
        "alpha": "alpha",
        "b": "beta",
        "beta": "beta",
        "rc": "rc",
    }
    normalized_stage = None
    if stage is not None:
        if stage not in prerelease_options:
            LOGGER.error(
                'Invalid stage "%s". Must be one of: %s',
                stage,
                ", ".join(("alpha", "beta", "rc")),
            )
            sys.exit(1)
        normalized_stage = prerelease_options[stage]

    # Bump version using dunamai
    if last_tag == "v0.0.0":
        # No real tags yet; bump from 0.0.0
        base_version = Version.parse("0.0.0")
        new_version = base_version.bump(component_index)
    else:
        new_version = Version.from_git().bump(component_index)

    if normalized_stage is not None:
        if new_version.stage != normalized_stage:
            new_version.stage = normalized_stage
            new_version.revision = 1
        elif new_version.revision is None:
            new_version.revision = 1

    # Serialize without dirty flag for clean release tags
    serialized = new_version.serialize(style=Style.Pep440)
    LOGGER.info("Bumping version to %s", serialized)
    _run_command(["git", "tag", f"v{serialized}"])
