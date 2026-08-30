import ast
import logging
import os
import re
import tomllib
from collections.abc import Sequence
from functools import lru_cache
from importlib import metadata
from pathlib import Path
from typing import Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import Version

from . import utils

LOGGER = logging.getLogger(__name__)

PUBLISH_REPOSITORY_ENV_VAR = "COMMON_PYTHON_TASKS_PUBLISH_REPOSITORY"
PUBLISH_REPOSITORY_URL_ENV_VAR = "COMMON_PYTHON_TASKS_PUBLISH_URL"
PUBLISH_REPOSITORY_ENV_VARS = (
    PUBLISH_REPOSITORY_ENV_VAR,
    "UV_PUBLISH_INDEX",
)
PUBLISH_URL_ENV_VARS = (
    PUBLISH_REPOSITORY_URL_ENV_VAR,
    "UV_PUBLISH_URL",
)


def _parse_tool_version_output(output: str, tool_name: str) -> str:
    cleaned_output = output.strip()
    if not cleaned_output:
        utils.fatal(f"Unable to determine {tool_name} version from empty output")

    match = re.search(r"(\d+\.\d+\.\d+(?:[-+._a-zA-Z0-9]*)?)", cleaned_output)
    if match is not None:
        return match.group(1)

    tokens = cleaned_output.replace("(", " ").replace(")", " ").split()
    if tokens:
        return tokens[-1]

    utils.fatal(f"Unable to parse {tool_name} version output: {output!r}")


def _find_non_empty_env_override(env_vars: Sequence[str]) -> tuple[str, str] | None:
    for env_var in env_vars:
        value = os.getenv(env_var)
        if value is not None and value.strip():
            return env_var, value.strip()
    return None


def _resolve_uv_publish_repository_from_config() -> str | None:
    pyproject_data = read_pyproject_toml()
    uv_config = pyproject_data.get("tool", {}).get("uv", {})
    raw_indexes = uv_config.get("index")
    if raw_indexes is None:
        return None

    if not isinstance(raw_indexes, list):
        LOGGER.warning(
            "Ignoring malformed [tool.uv.index] configuration: expected a list of tables"
        )
        return None

    publishable_indexes = [
        entry
        for entry in raw_indexes
        if isinstance(entry, dict)
        and isinstance(entry.get("name"), str)
        and entry.get("name", "").strip()
        and isinstance(entry.get("publish-url"), str)
        and entry.get("publish-url", "").strip()
    ]
    if not publishable_indexes:
        return None

    default_publishable_names = [
        entry["name"].strip()
        for entry in publishable_indexes
        if entry.get("default") is True
    ]
    if len(default_publishable_names) > 1:
        utils.fatal(
            "Multiple publishable `[[tool.uv.index]]` entries are marked `default = true`. "
            "Set one default publishable index or pass an explicit publish repository."
        )
    if len(default_publishable_names) == 1:
        return default_publishable_names[0]

    publishable_names = [entry["name"].strip() for entry in publishable_indexes]
    if len(publishable_names) == 1:
        return publishable_names[0]

    utils.fatal(
        "Multiple publishable `[[tool.uv.index]]` entries were found. "
        "Set one as `default = true` or pass an explicit publish repository."
    )


def _resolve_default_publish_target() -> tuple[str | None, str | None]:
    repository_override = _find_non_empty_env_override(PUBLISH_REPOSITORY_ENV_VARS)
    if repository_override is not None:
        env_var, repository_name = repository_override
        LOGGER.debug("Using uv publish index %s from %s", repository_name, env_var)
        return repository_name, None

    config_repository_name = _resolve_uv_publish_repository_from_config()
    if config_repository_name is not None:
        LOGGER.debug(
            "Using uv publish index %s from [[tool.uv.index]] configuration",
            config_repository_name,
        )
        return config_repository_name, None

    repository_url_override = _find_non_empty_env_override(PUBLISH_URL_ENV_VARS)
    if repository_url_override is None:
        return None, None

    env_var, repository_url = repository_url_override
    LOGGER.debug("Using uv publish URL %s from %s", repository_url, env_var)
    return None, repository_url


def get_build_command(wheel_only: bool = False) -> list[str]:
    """Return the uv package build command.

    Args:
        wheel_only: Whether to build only a wheel artifact.

    Returns:
        Command tokens for the package build command.
    """
    command = ["uv", "build"]
    if wheel_only:
        command.append("--wheel")
    return command


def get_dependency_update_command(
    dependencies: Sequence[str] | None = None,
) -> list[str]:
    """Return the uv dependency update command.

    Args:
        dependencies: Optional dependency names to update. When omitted, all
            dependencies are updated.

    Returns:
        Command tokens for the dependency update command.
    """
    if dependencies is None:
        dependencies = []

    command = ["uv", "sync", "--upgrade"]
    for dependency in dependencies:
        command.extend(["--upgrade-package", dependency])
    return command


def get_publish_command(
    repository: str | None = None,
    repository_url: str | None = None,
) -> list[str]:
    """Return the uv package publish command.

    Args:
        repository: Optional configured repository name to publish to.
        repository_url: Optional repository upload URL to publish to.

    Returns:
        Command tokens for the package publish command.
    """
    if repository is not None and repository_url is not None:
        utils.fatal("Specify either `repository` or `repository_url`, not both.")

    if repository is None and repository_url is None:
        repository, repository_url = _resolve_default_publish_target()

    command = ["uv", "publish"]
    if repository_url is not None:
        command += ["--publish-url", repository_url]
    elif repository is not None:
        command += ["--index", repository]
    return command


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


@lru_cache
def get_uv_version() -> str:
    """Return the installed uv version string.

    Returns:
        The uv version parsed from the output of `uv --version`.
    """
    return _parse_tool_version_output(
        utils.run_command(["uv", "--version"], capture_output=True).stdout,
        tool_name="uv",
    )


def _query_uv_runtime_version(candidate: str) -> str | None:
    result = utils.run_command(
        [
            "uv",
            "run",
            "python",
            "-c",
            "import importlib.metadata, sys; print(importlib.metadata.version(sys.argv[1]))",
            candidate,
        ],
        capture_output=True,
        acceptable_returncodes={0, 1},
    )
    if result is not None and result.returncode == 0:
        return result.stdout.strip() or None
    return None


def _parse_package_show_version(output: str) -> str | None:
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip().lower() == "version":
            return value.strip()
    return None


@lru_cache
def get_installed_requirement_version(requirement_name: str) -> str | None:
    """Return the installed version for a Python requirement name.

    This helper is intended for dependencies that should already be available in
    the active Python environment, such as development tools installed in the
    current virtualenv.

    It normalizes extras like `package[extra]` and tries common name variants
    with hyphens and underscores. If the package is not available to
    importlib.metadata, it falls back to uv runtime and package listing commands.

    Args:
        requirement_name: The requirement name to lookup.

    Returns:
        The installed version string, or `None` if the package cannot be resolved.
    """
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

    for candidate in candidates:
        version = _query_uv_runtime_version(candidate)
        if version:
            return version

    result = utils.run_command(
        ["uv", "pip", "show", package_name],
        capture_output=True,
        acceptable_returncodes={0, 1},
    )
    if result.returncode == 0:
        return _parse_package_show_version(result.stdout)
    return None


@lru_cache
def read_pyproject_toml() -> dict[str, Any]:
    """Read and parse the `pyproject.toml` file.

    Returns:
        A dictionary representing the contents of the `pyproject.toml` file.
    """
    return tomllib.loads(Path("pyproject.toml").read_text())


RUFF_TARGET_PYTHON_MINORS = range(7, 16)


def _specifier_supports_python_minor(specifier_set: SpecifierSet, minor: int) -> bool:
    return any(
        specifier_set.contains(Version(f"3.{minor}.{patch}")) for patch in range(1000)
    )


def get_ruff_target_version() -> str | None:
    """Return the Ruff target-version token based on `project.requires-python`.

    Returns:
        The lowest supported Python version in Ruff format, such as
        `py311`, or `None` when the project metadata is missing or invalid.
    """
    requires_python = read_pyproject_toml().get("project", {}).get("requires-python")
    if not isinstance(requires_python, str):
        return None

    try:
        specifier_set = SpecifierSet(requires_python)
    except InvalidSpecifier:
        LOGGER.warning("Unable to parse requires-python specifier: %s", requires_python)
        return None

    for minor in RUFF_TARGET_PYTHON_MINORS:
        if _specifier_supports_python_minor(specifier_set, minor):
            return f"py3{minor}"
    return None


@lru_cache
def has_debug_dependency_group() -> bool:
    """Return whether `pyproject.toml` declares a non-empty debug dependency group.

    Returns:
        `True` when `[dependency-groups].debug` exists and has entries.
    """
    debug_group = read_pyproject_toml().get("dependency-groups", {}).get("debug")
    if isinstance(debug_group, (list, tuple, set)):
        return bool(debug_group)
    return bool(debug_group)


def _get_project_scripts() -> dict[str, str]:
    scripts = read_pyproject_toml().get("project", {}).get("scripts")
    if not isinstance(scripts, dict):
        return {}

    normalized_scripts = {
        str(script_name).strip(): str(script_target)
        for script_name, script_target in scripts.items()
        if str(script_name).strip()
    }
    return normalized_scripts


def _get_available_container_entrypoint_scripts() -> tuple[str, ...]:
    return tuple(sorted(_get_project_scripts().keys()))


def resolve_container_entrypoint_command(entrypoint_script: str | None = None) -> str:
    """Resolve the command used in the generated container entrypoint script.

    Args:
        entrypoint_script: Optional explicit entrypoint script override.

    Returns:
        A command name to place in `/pkg/entrypoint.sh`.
    """

    available_scripts = _get_available_container_entrypoint_scripts()
    scripts_set = set(available_scripts)

    if entrypoint_script is not None and entrypoint_script.strip():
        selected_entrypoint = entrypoint_script.strip()
        if selected_entrypoint in scripts_set:
            return selected_entrypoint

        if available_scripts:
            utils.fatal(
                "Invalid CONTAINER_CUSTOM_ENTRYPOINT value "
                f"{selected_entrypoint!r}. "
                "It must match a key in [project].scripts. "
                f"Available scripts: {', '.join(available_scripts)}"
            )

        utils.fatal(
            "Invalid CONTAINER_CUSTOM_ENTRYPOINT value "
            f"{selected_entrypoint!r}. "
            "No [project].scripts entries were found in pyproject.toml."
        )

    script_name = utils.get_package_name(use_underscores=True)
    hyphenated_name = script_name.replace("_", "-") if script_name else None
    for candidate in filter(None, [script_name, hyphenated_name]):
        if candidate in scripts_set:
            return candidate

    return "python"


def _extract_tags_from_script_argument(
    script_value: str, script_key: str, argument_key: str
) -> set[str] | None:
    pattern = re.compile(rf"{re.escape(argument_key)}\s*=\s*(\[[^\]]*\])")
    match = pattern.search(script_value)
    if match is None:
        return None

    try:
        parsed = ast.literal_eval(match.group(1))
    except (ValueError, SyntaxError):
        LOGGER.warning(
            "Failed to parse %s from tool.poe.%s: %s",
            argument_key,
            script_key,
            script_value,
        )
        return None

    if not isinstance(parsed, (list, tuple, set)):
        return None

    return {str(tag).strip() for tag in parsed if str(tag).strip()}


def extract_poe_script_tags(
    include_script: str | None = None,
    exclude_script: str | None = None,
) -> tuple[set[str] | None, set[str] | None]:
    """Extract include and exclude tags from Poe script configuration.

    Args:
        include_script: The raw `tool.poe.include_script` value.
        exclude_script: The raw `tool.poe.exclude_script` value.

    Returns:
        A tuple containing parsed include and exclude tags. Each tuple value is
        a set of strings, or `None` when the corresponding tags are not present
        or cannot be parsed.
    """
    include_tags = None
    if isinstance(include_script, str):
        include_tags = _extract_tags_from_script_argument(
            include_script,
            script_key="include_script",
            argument_key="include_tags",
        )

    exclude_tags = None
    if isinstance(exclude_script, str):
        exclude_tags = _extract_tags_from_script_argument(
            exclude_script,
            script_key="exclude_script",
            argument_key="exclude_tags",
        )

    if exclude_tags is None and isinstance(include_script, str):
        exclude_tags = _extract_tags_from_script_argument(
            include_script,
            script_key="include_script",
            argument_key="exclude_tags",
        )

    return include_tags, exclude_tags


@lru_cache
def is_task_tag_included(tag: str) -> bool:
    """Return whether a task tag is included by current Poe script rules.

    Args:
        tag: The task tag to evaluate.

    Returns:
        `True` if the tag is included, `False` if it is excluded by Poe rules.
    """
    pyproject_data = read_pyproject_toml()

    poe_config = pyproject_data.get("tool", {}).get("poe", {})
    include_tags, exclude_tags = extract_poe_script_tags(
        include_script=poe_config.get("include_script"),
        exclude_script=poe_config.get("exclude_script"),
    )

    if include_tags is not None:
        return tag in include_tags

    if exclude_tags is not None:
        return tag not in exclude_tags

    return True


def _get_project_version_from_pyproject() -> str | None:
    """Return `project.version` from pyproject metadata when present.

    Returns:
        The configured `project.version`, or `None` if missing.
    """
    version = read_pyproject_toml().get("project", {}).get("version")
    if isinstance(version, str) and version.strip():
        return version.strip()
    return None


def get_project_version_from_vcs() -> str | None:
    """Return a PEP 440 version derived from VCS tags.

    Returns:
        A version string when git metadata is available; otherwise `None`.
    """
    try:
        from dunamai import Style, Version

        return Version.from_git().serialize(style=Style.Pep440, dirty=False)
    except (OSError, RuntimeError, ValueError):
        return None


def get_project_version() -> str:
    """Return the current project version for release and tagging workflows.

    Static `project.version` metadata takes precedence over a VCS-derived version.
    Placeholder static versions fall back to VCS metadata when available.

    Returns:
        The resolved current project version.
    """
    pyproject_version = _get_project_version_from_pyproject()
    if pyproject_version and pyproject_version not in {"0.0.0", "0.0.0.dev0"}:
        return pyproject_version

    vcs_version = get_project_version_from_vcs()
    if vcs_version is not None:
        return vcs_version

    if pyproject_version:
        LOGGER.warning(
            "Using placeholder project.version=%s because VCS version could not be resolved",
            pyproject_version,
        )
        return pyproject_version

    utils.fatal("Unable to determine project version from pyproject metadata or VCS")


def get_release_tag_from_project_version() -> str:
    """Return release tag string in `v<version>` form.

    Returns:
        Release tag prefixed with `v`.
    """
    return f"v{get_project_version()}"
