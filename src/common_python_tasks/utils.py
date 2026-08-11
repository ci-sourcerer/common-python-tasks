import importlib.util
import logging
import os
import re
import shutil
import subprocess
import sys
import tomllib
from functools import lru_cache
from getpass import getuser
from importlib.resources import files
from pathlib import Path
from shlex import quote
from typing import Collection, Sequence

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

    Returns:
        This function does not return because it terminates the process.
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
    """Log a dry-run informational message with a yellow prefix.

    Args:
        message: The log message template.
        *args: Values interpolated into the log message.
    """
    LOGGER.info("\033[93m[DRY RUN]\033[0m " + message, *args)


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
    acceptable_returncodes: Collection[int] | None = None,
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
    if acceptable_returncodes is None:
        acceptable_returncodes = {0}
    acceptable_returncodes = set(acceptable_returncodes)

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
        text = data_file.read_text()
        # Try to provide a real filesystem Path when possible (packages in wheels
        # may store resources inside archives). `as_file()` yields a real path
        # via a context manager when supported by the Traversable.
        try:
            with data_file.as_file() as real_path:
                return (Path(real_path), text)
        except (AttributeError, OSError):
            # Fall back to a Path constructed from the Traversable string
            # representation so existing callers that index [0] still receive
            # a Path-like object.
            return (Path(str(data_file)), text)
    except FileNotFoundError as e:
        if fatal_on_missing:
            fatal(f"Data file not found: {file_name} ({e})")
        return None


def normalize_registry(registry: str | None) -> str | None:
    """Normalize a container registry string for image reference composition.

    Args:
        registry: A registry string which may include a URL scheme or trailing
            slash.

    Returns:
        The normalized registry string without a scheme or trailing slash, or
        `None` when the input is empty.
    """
    if not registry:
        return None

    registry = registry.strip()
    if not registry:
        return None

    for prefix in ("https://", "http://"):
        if registry.startswith(prefix):
            registry = registry[len(prefix) :]

    return registry.rstrip("/")


def get_registry_username() -> str:
    """Get the container registry username from environment or fallback.

    Returns:
        The configured registry username, falling back to the current system
        user.
    """
    return os.getenv("CONTAINER_REGISTRY_USERNAME") or getuser()


def get_registry_namespace() -> str | None:
    """Return the container registry namespace from the environment, if set.

    Returns:
        The configured namespace, or `None` when it is unset or blank.
    """
    namespace = os.getenv("CONTAINER_REGISTRY_NAMESPACE")
    return namespace.strip() if namespace and namespace.strip() else None


def get_container_registry_url() -> str:
    """Get the container registry URL from the environment or fallback.

    If `CONTAINER_REGISTRY_URL` is a host only and
    `CONTAINER_REGISTRY_NAMESPACE` is set, the namespace is appended.
    If `CONTAINER_REGISTRY_URL` already contains a namespace path, it is used
    as-is.

    Returns:
        The registry prefix, which may include a namespace such as
        `ghcr.io/org` or `docker.io/user`.
    """
    registry = normalize_registry(os.getenv("CONTAINER_REGISTRY_URL"))
    namespace = get_registry_namespace()

    if registry:
        if registry == "docker.io":
            if namespace:
                return normalize_registry(f"docker.io/{namespace}") or "docker.io"
            return "docker.io"
        if namespace and "/" not in registry:
            return f"{registry}/{namespace}"
        return registry

    if namespace:
        return normalize_registry(f"docker.io/{namespace}") or "docker.io"

    return f"docker.io/{get_registry_username()}"


def parse_image_reference(image_reference: str) -> dict[str, str | None]:
    """Parse a Docker image reference into registry, namespace, repository, and tag.

    Args:
        image_reference: A Docker image reference like
            `ghcr.io/org/repo:tag` or `repo:tag`.

    Returns:
        A dictionary containing parsed image components.
    """
    if not image_reference or not image_reference.strip():
        raise ValueError("Image reference must not be empty")

    from docker.utils import parse_repository_tag

    reference = image_reference.strip()

    # parse_repository_tag handles both @ (digest) and : (tag) separation
    name, tag_or_digest = parse_repository_tag(reference)

    # Distinguish digest from tag (digests are algorithm:encoded, e.g., sha256:...)
    tag = None
    digest = None
    if tag_or_digest:
        if tag_or_digest.startswith(("sha256:", "sha512:")):
            digest = tag_or_digest
        else:
            tag = tag_or_digest

    # Parse name into registry/namespace/repository
    parts = name.split("/")
    registry = None
    namespace = None
    repository = parts[-1]
    if len(parts) > 1 and (
        "." in parts[0] or ":" in parts[0] or parts[0] == "localhost"
    ):
        registry = parts[0]
        namespace = "/".join(parts[1:-1]) if len(parts) > 2 else None
    elif len(parts) > 1:
        namespace = "/".join(parts[:-1])

    return {
        "registry": registry,
        "namespace": namespace,
        "repository": repository,
        "tag": tag,
        "digest": digest,
    }


def compose_image_name(
    repository: str,
    tag: str | None = None,
    registry: str | None = None,
    namespace: str | None = None,
    fully_qualified: bool = True,
) -> str:
    """Compose a Docker image name from registry, namespace, repository, and tag.

    Args:
        repository: The repository name.
        tag: Optional image tag.
        registry: Optional registry prefix, e.g. `ghcr.io` or `ghcr.io/org`.
        namespace: Optional namespace to include when registry does not already
            contain one.
        fully_qualified: Whether to return the fully-qualified image reference.

    Returns:
        A Docker image reference string.
    """
    if not repository:
        raise ValueError("Repository name is required")

    registry_prefix = normalize_registry(registry) if registry else None
    if registry_prefix and namespace and "/" in registry_prefix:
        LOGGER.debug(
            "Registry '%s' already includes a namespace; ignoring CONTAINER_REGISTRY_NAMESPACE",
            registry_prefix,
        )
        namespace = None

    if fully_qualified:
        if registry_prefix:
            if namespace:
                registry_prefix = f"{registry_prefix}/{namespace}"
            image_name = f"{registry_prefix}/{repository}"
        elif namespace:
            image_name = f"{namespace}/{repository}"
        else:
            image_name = repository
    else:
        image_name = f"{namespace}/{repository}" if namespace else repository

    return f"{image_name}:{tag}" if tag else image_name


@lru_cache
def get_package_name(use_underscores: bool = False) -> str | None:
    """Return the package name from environment or pyproject configuration.

    Args:
        use_underscores: Whether to normalize hyphenated names to underscores.

    Returns:
        The package name, with hyphens replaced by underscores if requested.
    """
    import tomllib

    name = os.getenv("PACKAGE_NAME")
    if not name:
        try:
            pyproject = Path("pyproject.toml")
            if pyproject.exists():
                name = (
                    tomllib.loads(pyproject.read_text()).get("project", {}).get("name")
                )
        except Exception as e:  # pragma: no cover - defensive logging
            LOGGER.debug("Unable to read pyproject.toml: %s", e)

    if use_underscores and name:
        name = package_name_to_underscore(name)
    return name


def get_full_image_name() -> str:
    """Return the full container image name for the current package.

    Returns:
        The fully qualified image name including registry and package name.
    """
    package_name = get_package_name()
    if package_name is None:
        return get_container_registry_url()

    return compose_image_name(
        package_name,
        registry=get_container_registry_url(),
        fully_qualified=True,
    )


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
        type_identifier: Bundled data directory that contains the fallback file.

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


def _has_discoverable_ruff_config() -> bool:
    for directory in (Path.cwd(), *Path.cwd().parents):
        if any(
            (directory / filename).is_file() for filename in (".ruff.toml", "ruff.toml")
        ):
            return True

        pyproject_path = directory / "pyproject.toml"
        if pyproject_path.is_file() and "ruff" in tomllib.loads(
            pyproject_path.read_text()
        ).get("tool", {}):
            return True
    return False


def get_ruff_config_path() -> tuple[Path | None, bool]:
    """Resolve the Ruff configuration used by the common tasks.

    Returns:
        A tuple containing an explicit configuration path, if needed, and whether
        that path refers to the bundled default configuration.
    """
    if os.getenv("RUFF_CONFIG"):
        return Path(os.environ["RUFF_CONFIG"]), False
    if _has_discoverable_ruff_config():
        return None, False
    return Path(load_data_file("ruff.toml")[0]), True


def render_template_text(
    template_text: str,
    extra_template_vars: dict[str, str] | None = None,
) -> str:
    """Render a Jinja2 template string with optional template variables.

    Args:
        template_text: Jinja2 template text to render.
        extra_template_vars: Optional values available to the template.

    Returns:
        The rendered template text.
    """
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
    config_path = get_config_path(
        "GIT_CLIFF_CONFIG",
        "cliff.toml",
        "cliff.toml",
    )
    return run_command(
        ["git-cliff", "--config", config_path if config_path else None, *args],
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
    res = run_git_cliff(["--unreleased", "--tag", tag_name], capture_output=True)
    release_notes = res.stdout if (res and res.stdout) else ""
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
    """Generate release notes from git-cliff for unreleased commits.

    Returns:
        Generated release notes, or `None` when git-cliff produces no content.
    """
    res = run_git_cliff(["--unreleased"], capture_output=True)
    if not res or not res.stdout:
        LOGGER.warning("git-cliff produced no release notes for unreleased commits")
        return None

    result = res.stdout
    return re.sub(
        r"(?im)\A##\s*\[?unreleased\]?\s*\n?",
        "",
        result,
        count=1,
    ).strip()


def confirm(message: str) -> bool:
    """Prompt the user for a yes/no confirmation.

    Args:
        message: The confirmation message to display.

    Returns:
        `True` if the user confirms with 'y' or 'yes', `False` for 'n', 'no', or empty
        input. The prompt will repeat until a valid response is received.
    """
    yes_values = {"y", "yes"}
    no_values = {"n", "no"}
    while True:
        try:
            response = input(f"{message} [y/N]: ").strip().lower()
        except (EOFError, OSError):
            return False

        if response in yes_values:
            return True
        if response in no_values:
            return False
