import re
import tomllib
from functools import lru_cache
from importlib import metadata
from pathlib import Path
from typing import Any

from . import utils


@lru_cache
def get_authors() -> list[tuple[str, str]]:
    """Return a list of authors from the pyproject.toml file.

    Returns:
        A list of tuples containing the name and email of each author.
    """
    authors = read_pyproject_toml().get("project", {}).get("authors", [])
    return [
        ((a.get("name") or "").strip(), (a.get("email") or "").strip().strip("<>"))
        for a in authors
    ]


def get_local_poetry_plugin_version(package_name: str) -> str | None:
    """Return a version from the local Poetry plugin installation if present.

    Args:
        package_name: The name of the package to check.

    Returns:
        The version of the local Poetry plugin if present, None otherwise.
    """

    plugins_dir = Path(".poetry/plugins")
    if not plugins_dir.is_dir():
        return None

    candidates = {
        package_name,
        utils.package_name_to_underscore(package_name),
        package_name.replace("_", "-"),
    }

    for metadata_path in plugins_dir.glob("*.dist-info/METADATA"):
        try:
            metadata_text = metadata_path.read_text(encoding="utf-8")
        except OSError:
            continue

        name = None
        version = None
        for line in metadata_text.splitlines():
            if line.startswith("Name:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("Version:"):
                version = line.split(":", 1)[1].strip()
            if name is not None and version is not None:
                break

        if name and version and name in candidates:
            return version
    return None


@lru_cache
def get_poetry_version() -> str:
    """Return the installed Poetry version string.

    Returns:
        The Poetry version parsed from the output of `poetry --version`.
    """
    return (
        utils.run_command(["poetry", "--version"], capture_output=True)
        .stdout.strip()
        .split()[-1]
    )[0:-1]


@lru_cache
def get_installed_requirement_version(requirement_name: str) -> str | None:
    """Return the installed version for a Python requirement name.

    This helper is intended for dependencies that should already be available in
    the active Python environment, such as development tools installed in the
    current virtualenv.

    It normalizes extras like `package[extra]` and tries common name variants
    with hyphens and underscores. If the package is not available to
    importlib.metadata, it falls back to `poetry show` and then
    `poetry self show`.

    Args:
        requirement_name: The requirement name to lookup.

    Returns:
        The installed version string, or `None` if the package cannot be resolved.
    """
    package_name = requirement_name.split("[", 1)[0]

    package_name = requirement_name.split("[", 1)[0]
    candidates = {
        package_name,
        utils.package_name_to_underscore(package_name),
        package_name.replace("_", "-"),
    }

    for candidate in candidates:
        try:
            return metadata.version(candidate)
        except metadata.PackageNotFoundError:
            pass

    def _query_poetry_runtime_version(candidate: str) -> str | None:
        result = utils.run_command(
            [
                "poetry",
                "run",
                "python",
                "-c",
                f"from importlib import metadata; print(metadata.version({candidate!r}))",
            ],
            capture_output=True,
            acceptable_returncodes={0, 1},
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            if version:
                return version
        return None

    version = get_local_poetry_plugin_version(package_name)
    if version:
        return version

    for candidate in candidates:
        version = _query_poetry_runtime_version(candidate)
        if version:
            return version

    def _parse_poetry_show_version(output: str) -> str | None:
        for line in output.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            if key.strip() == "version":
                return value.strip()
        return None

    for cmd in (
        ["poetry", "show", package_name],
        ["poetry", "self", "show", package_name],
    ):
        result = utils.run_command(
            cmd,
            capture_output=True,
            acceptable_returncodes={0, 1},
        )
        if result.returncode == 0:
            version = _parse_poetry_show_version(result.stdout)
            if version:
                return version
    return None


@lru_cache
def read_pyproject_toml() -> dict[str, Any]:
    """Read and parse the `pyproject.toml` file.

    Returns:
        A dictionary representing the contents of the `pyproject.toml` file.
    """
    return tomllib.loads(Path("pyproject.toml").read_text())


@lru_cache
def has_debug_dependency_group() -> bool:
    """Return whether `pyproject.toml` declares a non-empty debug dependency group.

    Returns:
        True when `[dependency-groups].debug` exists and has entries.
    """
    debug_group = read_pyproject_toml().get("dependency-groups", {}).get("debug")
    if isinstance(debug_group, (list, tuple, set)):
        return bool(debug_group)
    return bool(debug_group)


def resolve_container_entrypoint_command(custom_entrypoint: str | None = None) -> str:
    """Resolve the command used in the generated container entrypoint script.

    Args:
        custom_entrypoint: Optional explicit command override.

    Returns:
        A command name to place in `/pkg/entrypoint.sh`.
    """

    if custom_entrypoint is not None and custom_entrypoint.strip():
        return custom_entrypoint.strip()

    script_name = utils.get_package_name(use_underscores=True)
    scripts = read_pyproject_toml().get("project", {}).get("scripts")
    if isinstance(scripts, dict) and script_name in scripts:
        return script_name

    return "python"


def extract_poe_script_tags(include_script: str, argument_name: str) -> set[str] | None:
    """Extract a tag list argument from a Poe include_script expression.

    Args:
        include_script: The raw Poe include_script value.
        argument_name: The argument name to extract, such as `include_tags` or
            `exclude_tags`.

    Returns:
        A set of parsed tag strings, or `None` if parsing fails.
    """
    import ast

    match = re.search(rf"{argument_name}\s*=\s*(\[[^\]]*\])", include_script)
    if match is None:
        return None

    try:
        parsed = ast.literal_eval(match.group(1))
    except (ValueError, SyntaxError):
        utils.LOGGER.warning(
            "Failed to parse %s from tool.poe.include_script: %s",
            argument_name,
            include_script,
        )
        return None

    if not isinstance(parsed, (list, tuple, set)):
        return None

    return {str(tag).strip() for tag in parsed if str(tag).strip()}


@lru_cache
def is_task_tag_included(tag: str) -> bool:
    """Return whether a task tag is included by current Poe include_script rules.

    Args:
        tag: The task tag to evaluate.

    Returns:
        True if the tag is included, False if it is excluded by Poe include_script.
    """
    pyproject_data = read_pyproject_toml()

    include_script = pyproject_data.get("tool", {}).get("poe", {}).get("include_script")
    if not isinstance(include_script, str):
        return True

    include_tags = extract_poe_script_tags(include_script, "include_tags")
    if include_tags is not None:
        return tag in include_tags

    exclude_tags = extract_poe_script_tags(include_script, "exclude_tags")
    if exclude_tags is not None:
        return tag not in exclude_tags

    return True


def get_project_version_from_poetry() -> str:
    """Return the project version parsed from `poetry version` output.

    Returns:
        The parsed project version string.
    """
    poetry_version_output = utils.run_command(
        ["poetry", "version"],
        capture_output=True,
        acceptable_returncodes={0},
    ).stdout.strip()
    if not poetry_version_output:
        utils.fatal("Unable to determine project version from poetry version")

    parts = poetry_version_output.rsplit(" ", 1)
    if len(parts) != 2 or not parts[1].strip():
        utils.fatal(
            "Unexpected poetry version output format: " f"{poetry_version_output!r}"
        )
    return parts[1].strip()


def get_release_tag_from_poetry_version() -> str:
    """Return release tag string in `v<version>` form from Poetry metadata.

    Returns:
        The release tag string prefixed with `v`.
    """
    return f"v{get_project_version_from_poetry()}"
