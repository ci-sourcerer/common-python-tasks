import importlib.util
import logging
import os
import re
import shutil
import subprocess
import sys
from functools import lru_cache
from getpass import getuser
from importlib.resources import files
from pathlib import Path
from shlex import quote
from typing import Callable, Sequence

from jinja2 import Template

LOGGER = logging.getLogger(__name__)


def package_name_to_underscore(package_name: str) -> str:
    """Convert a package name to an underscore-separated name for importlib.

    Args:
        package_name: The original package name, which may contain hyphens.

    Returns:
        The package name with hyphens replaced by underscores.
    """
    return package_name.replace("-", "_")


@lru_cache
def is_package_installed(package_name: str) -> bool:
    """Check if a package is installed and can be imported.

    Args:
        package_name: The name of the package to check.

    Returns:
        `True` if the package is installed, `False` otherwise.
    """
    is_installed = (
        importlib.util.find_spec(package_name_to_underscore(package_name)) is not None
    )
    if not is_installed:
        LOGGER.debug("%s is not installed", package_name)

    return is_installed


def fatal(message: str, exit_code: int = 1) -> None:
    """Log a critical error message and exit the program.

    Args:
        message: The error message to log.
        exit_code: The exit code to use when terminating the program.
    """
    LOGGER.critical(message)
    sys.exit(exit_code)


def require_package(package_name: str) -> None:
    """Ensure that a package is installed.

    Args:
        package_name: The name of the package to check.
    """
    if not is_package_installed(package_name):
        fatal(f"{package_name} is not installed")


def log_dry_run(message: str, *args: object) -> None:
    """Log a dry-run informational message with a yellow prefix."""
    LOGGER.info("\033[93m[DRY RUN]\033[0m " + message, *args)


def run_available_tools(
    tools: list[tuple[Callable[..., None], str]], none_available_message: str
) -> None:
    """Run a list of tools if they are available.

    Args:
        tools: A list of tuples containing a callable and the name of the required
            package.
        none_available_message: The message to log if none of the tools are available.
    """
    ran_any = False
    for fn, package in tools:
        if is_package_installed(package):
            fn()
            ran_any = True
    if not ran_any:
        fatal(none_available_message)


def directory_has_contents(path: Path) -> bool:
    """Return whether a directory exists and contains at least one entry.

    Args:
        path: The directory to inspect.

    Returns:
        `True` when the directory exists and is not empty, otherwise `False`.
    """
    return path.is_dir() and any(path.iterdir())


def remove_path(path: Path) -> None:
    """Remove a file or directory if it exists.

    Args:
        path: The file or directory to remove.
    """
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def run_command(
    command: Sequence[str | Path | None],
    capture_output: bool = False,
    acceptable_returncodes: Sequence[int] | None = None,
    env: dict[str, str] | None = None,
    always_show_command: bool = False,
    dry_run: bool = False,
) -> subprocess.CompletedProcess | None:
    """Run a command as a subprocess and handle errors.

    Args:
        command: The command to run, as a sequence of strings or Paths. None values
            will be filtered out.
        capture_output: Whether to capture stdout and stderr.
        acceptable_returncodes: A set of acceptable return codes. If the command exits
            with a code not in this set, it will be treated as an error.
        env: An optional dictionary of environment variables to set for the command.
            This will be merged with the current environment.
        always_show_command: If `True`, log the command with INFO when not in dry-run
            mode.
        dry_run: If `True`, log the command without executing it.

    Returns:
        The `CompletedProcess` instance from the subprocess run, or `None` for dry-run
        invocations.
    """
    import subprocess

    if acceptable_returncodes is None:
        acceptable_returncodes = {0}

    command = [str(c) for c in command if c is not None]

    bold_command_display = (
        f"\033[1m{' '.join([quote(str(arg)) for arg in command])}\033[0m"
    )
    if always_show_command:
        LOGGER.info("Running command: %s", bold_command_display)
    else:
        LOGGER.debug("Running command: %s", bold_command_display)

    if dry_run:
        log_dry_run("Would run command: %s", " ".join(command))
        return None

    merged_env = {**os.environ, **env} if env is not None else None

    out = subprocess.run(
        command, capture_output=capture_output, text=True, env=merged_env
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
        LOGGER.critical(
            "Command failed (exit code %d): %s%s",
            out.returncode,
            bold_command_display,
            details,
        )

        import sys

        sys.exit(out.returncode)
    return out


def load_data_file(
    file_name: str, type_identifier: str = "generic", fatal_on_missing: bool = True
) -> tuple[Path, str] | None:
    """Load a data file from the package resources.

    Args:
        file_name: The name of the data file to load.
        type_identifier: The type of data file.
        fatal_on_missing: Whether to raise an error if the file is not found.

    Returns:
        A tuple containing the `Path` to the data file and its contents as a string, or
            `None` if the file is not found and fatal_on_missing is `False`.
    """
    try:
        data_files = files("common_python_tasks") / "data" / type_identifier
        data_file = data_files / file_name
        return (Path(str(data_file)), data_file.read_text())
    except FileNotFoundError as e:
        if fatal_on_missing:
            fatal(f"Data file not found: {file_name} ({e})")
        return None


def get_dockerhub_username() -> str:
    """Get the Docker Hub username from the environment variable or fallback to the
    current system user.

    Returns:
        The Docker Hub username as a string.
    """
    return os.getenv("DOCKERHUB_USERNAME") or getuser()


def get_container_registry_url() -> str:
    """Get the container registry URL from the environment variable or fallback to
    Docker Hub with the username.

    Returns:
        The container registry URL as a string.
    """
    return os.environ.get(
        "CONTAINER_REGISTRY_URL",
        f"docker.io/{get_dockerhub_username()}",
    ).strip()


@lru_cache
def get_package_name(use_underscores: bool = False) -> str:
    """Return the package name from environment or pyproject configuration.

    Args:
        use_underscores: Whether to normalize hyphenated names to underscores.

    Returns:
        The package name, with hyphens replaced by underscores if requested.
    """
    import tomllib

    name = os.getenv("PACKAGE_NAME") or tomllib.loads(
        Path("pyproject.toml").read_text()
    ).get("project", {}).get("name")
    if use_underscores and name:
        name = package_name_to_underscore(name)
    return name


def get_full_image_name() -> str:
    """Return the full container image name for the current package.

    Returns:
        The fully qualified image name including registry and package name.
    """
    return f"{get_container_registry_url()}/{get_package_name()}"


def get_config_path(
    env_var_name: str,
    local_config_filename: str,
    data_config_filename: str,
    tool_name: str | None = None,
    type_identifier: str = "generic",
) -> Path | None:
    """Get the path to a configuration file.

    Checks for configuration in the following order:
    1. If tool_name provided, check if `tool.{tool_name}` exists in `pyproject.toml`
       - If it exists, return `None` (use `pyproject.toml` config)
    2. Check environment variable
    3. Check for local config file
    4. Fall back to bundled data file

    Args:
        env_var_name: Name of the environment variable to check.
        local_config_filename: Name of the local config file to look for.
        data_config_filename: Name of the bundled config file to use as fallback.
        tool_name: Optional tool name to check in `pyproject.toml` under `[tool.{tool_name}]`.

    Returns:
        `Path` to config file, or `None` if config exists in `pyproject.toml`
    """
    if tool_name is not None:
        from .project import read_pyproject_toml

        pyproject_data = read_pyproject_toml()
        if pyproject_data.get("tool", {}).get(tool_name):
            LOGGER.debug("Using [tool.%s] configuration from pyproject.toml", tool_name)
            return None

    if os.getenv(env_var_name):
        config_path = Path(os.getenv(env_var_name))
        LOGGER.debug("Using config from %s: %s", env_var_name, config_path)
        return config_path

    local_config_path = Path(local_config_filename)
    if local_config_path.exists():
        LOGGER.debug("Using local config file: %s", local_config_path)
        return local_config_path

    bundled_config = load_data_file(
        data_config_filename, type_identifier=type_identifier
    )
    config_path = Path(bundled_config[0])
    LOGGER.debug("Using bundled config file: %s", config_path)
    return config_path


def render_template_text(
    template_text: str,
    extra_template_vars: dict[str, str] | None = None,
) -> str:
    """Render a Jinja2 template string with optional template variables."""
    template_vars = {**extra_template_vars} if extra_template_vars else {}
    return Template(template_text).render(**template_vars)


def run_git_cliff(
    args: Sequence[str | Path],
    capture_output: bool = False,
) -> subprocess.CompletedProcess | None:
    """Run git-cliff with the given arguments.

    Args:
        args: Additional arguments to pass to git-cliff.
        capture_output: Whether to capture stdout and stderr.

    Returns:
        The `CompletedProcess` result, or `None` for dry-run invocations.
    """
    return run_command(
        ["git-cliff", *args],
        capture_output=capture_output,
        acceptable_returncodes={0},
    )


def get_prepended_changelog_contents(
    tag_name: str,
    changelog_path: Path = Path("CHANGELOG.md"),
) -> str:
    """Return changelog content with release notes prepended for the given tag.

    Args:
        tag_name: The release tag to generate changelog entries for.
        changelog_path: The changelog file to read as the base content.

    Returns:
        The full changelog text as it would look after prepending release notes.
    """
    existing_changelog = (
        changelog_path.read_text(encoding="utf-8")
        if changelog_path.exists()
        else "# Changelog\n\n## [Unreleased]\n"
    )
    release_notes = run_git_cliff(
        ["--unreleased", "--tag", tag_name], capture_output=True
    ).stdout
    if release_notes.strip():
        # Ensure the prepended section is separated from existing content.
        release_notes = release_notes.rstrip("\n") + "\n\n"
    else:
        release_notes = ""

    return release_notes + existing_changelog


def prepend_changelog(
    tag_name: str,
    changelog_path: Path = Path("CHANGELOG.md"),
) -> None:
    """Prepend release notes for the given tag to a changelog file using git-cliff.

    Creates the changelog file with a scaffold header if it does not exist, then
    prepends the `git-cliff --unreleased --tag <tag_name>` output to the file.

    Args:
        tag_name: The release tag to generate changelog entries for.
        changelog_path: The path to the changelog file to prepend to.
    """
    changelog_path.write_text(
        get_prepended_changelog_contents(tag_name, changelog_path),
        encoding="utf-8",
    )


def changelog() -> str | None:
    """Generate release notes from git-cliff for unreleased commits."""
    result = run_git_cliff(["--unreleased"], capture_output=True).stdout
    if not result:
        LOGGER.warning("git-cliff produced no release notes for unreleased commits")
        return result

    return re.sub(
        r"(?im)\A##\s*\[?unreleased\]?\s*\n?",
        "",
        result,
        count=1,
    ).strip()
