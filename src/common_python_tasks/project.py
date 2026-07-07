import ast
import logging
import os
import re
import shutil
import tomllib
from enum import StrEnum, auto
from functools import lru_cache
from importlib import metadata
from pathlib import Path
from typing import Any

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from . import utils

LOGGER = logging.getLogger(__name__)

PACKAGE_MANAGER_ENV_VAR = "COMMON_PYTHON_TASKS_PACKAGE_MANAGER"
PACKAGE_MANAGER_ENV_VARS = (
    PACKAGE_MANAGER_ENV_VAR,
    "COMMON_PYTHON_TASKS_BUILD_TOOL",
    "PACKAGE_MANAGER",
)


class PackageManager(StrEnum):
    """Supported package-manager backends for build and publish workflows."""

    POETRY = auto()
    UV = auto()
    AUTO = auto()


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


def _find_package_manager_override() -> tuple[str, str] | None:
    for env_var in PACKAGE_MANAGER_ENV_VARS:
        value = os.getenv(env_var)
        if value is not None and value.strip():
            return env_var, value.strip().lower()
    return None


def _ensure_package_manager_available(package_manager: PackageManager) -> None:
    if shutil.which(package_manager) is None:
        utils.fatal(
            f"Requested package manager '{package_manager}' is not installed or not in PATH"
        )


def _detect_declared_package_manager(
    pyproject_data: dict[str, Any],
) -> PackageManager | None:
    build_backend = (
        pyproject_data.get("build-system", {}).get("build-backend", "") or ""
    )
    if isinstance(build_backend, str) and "poetry" in build_backend.lower():
        return PackageManager.POETRY

    if pyproject_data.get("tool", {}).get("poetry") is not None:
        return PackageManager.POETRY

    if pyproject_data.get("tool", {}).get("uv") is not None:
        return PackageManager.UV

    return None


def _resolve_package_manager_auto() -> tuple[PackageManager, str]:
    has_poetry = shutil.which("poetry") is not None
    has_uv = shutil.which("uv") is not None

    if has_uv and not has_poetry:
        return PackageManager.UV, "uv found and poetry missing"

    if has_poetry and not has_uv:
        return PackageManager.POETRY, "poetry found and uv missing"

    if not has_poetry and not has_uv:
        utils.fatal(
            "No supported package manager found in PATH. Install poetry or uv, "
            "or set one via COMMON_PYTHON_TASKS_PACKAGE_MANAGER."
        )

    pyproject_data = read_pyproject_toml()
    declared_manager = _detect_declared_package_manager(pyproject_data)
    if declared_manager is not None:
        return declared_manager, "project metadata"

    return PackageManager.POETRY, "default fallback"


@lru_cache
def get_package_manager() -> PackageManager:
    """Resolve the package manager backend used for build and publish commands.

    Resolution order:
    1. Environment overrides via `COMMON_PYTHON_TASKS_PACKAGE_MANAGER`,
       `COMMON_PYTHON_TASKS_BUILD_TOOL`, or `PACKAGE_MANAGER`, in that order.
    2. Auto-discovery from installed executables and project metadata.

    Supported values are `poetry`, `uv`, and `auto`.

    Returns:
        The selected package manager backend.
    """
    override = _find_package_manager_override()
    if override is None:
        package_manager, reason = _resolve_package_manager_auto()
        LOGGER.info(
            "Using package manager backend: %s (%s)",
            package_manager,
            reason,
        )
        return package_manager

    env_var, raw_value = override
    if raw_value not in PackageManager:
        utils.fatal(
            f"Invalid {env_var} value {raw_value!r}. " "Use one of: poetry, uv, auto."
        )

    if raw_value == PackageManager.AUTO:
        package_manager, reason = _resolve_package_manager_auto()
        LOGGER.info(
            "Using package manager backend: %s (%s via %s=%s)",
            package_manager,
            reason,
            env_var,
            raw_value,
        )
        return package_manager

    package_manager = PackageManager(raw_value)
    _ensure_package_manager_available(package_manager)
    LOGGER.info(
        "Using package manager backend: %s (from %s)",
        package_manager,
        env_var,
    )
    return package_manager


def get_package_manager_build_command(wheel_only: bool = False) -> list[str]:
    """Return the build command for the selected package manager.

    Args:
        wheel_only: Whether to build only a wheel artifact.

    Returns:
        Command tokens for the package build command.
    """
    package_manager = PackageManager(get_package_manager())
    if package_manager == PackageManager.UV:
        command = ["uv", "build"]
        if wheel_only:
            command.append("--wheel")
        return command

    command = ["poetry", "build"]
    if wheel_only:
        command += ["--format", "wheel"]
    return command


def get_package_manager_publish_command() -> list[str]:
    """Return the publish command for the selected package manager.

    Returns:
        Command tokens for the package publish command.
    """
    package_manager = PackageManager(get_package_manager())
    return [package_manager.value, "publish"]


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
    return _parse_tool_version_output(
        utils.run_command(["poetry", "--version"], capture_output=True).stdout,
        tool_name="poetry",
    )


def get_package_manager_version(package_manager: PackageManager | None = None) -> str:
    """Return the version string for the selected package manager.

    Args:
        package_manager: Optional explicit package manager backend.

    Returns:
        Parsed package-manager version.
    """
    selected_manager = PackageManager(package_manager or get_package_manager())
    if selected_manager == PackageManager.POETRY:
        return get_poetry_version()

    return _parse_tool_version_output(
        utils.run_command(
            [selected_manager.value, "--version"], capture_output=True
        ).stdout,
        tool_name=selected_manager.value,
    )


@lru_cache
def get_installed_requirement_version(requirement_name: str) -> str | None:
    """Return the installed version for a Python requirement name.

    This helper is intended for dependencies that should already be available in
    the active Python environment, such as development tools installed in the
    current virtualenv.

    It normalizes extras like `package[extra]` and tries common name variants
    with hyphens and underscores. If the package is not available to
    importlib.metadata, it falls back to package-manager runtime and package
    listing commands.

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

    package_manager = PackageManager(get_package_manager())

    def _query_runtime_version(candidate: str) -> str | None:
        result = utils.run_command(
            [
                package_manager,
                "run",
                "python",
                "-c",
                "import importlib.metadata, sys; print(importlib.metadata.version(sys.argv[1]))",
                candidate,
            ],
            capture_output=True,
            acceptable_returncodes={0, 1},
        )
        if result is None:
            return None
        if result.returncode == 0:
            version = result.stdout.strip()
            if version:
                return version
        return None

    if package_manager == PackageManager.POETRY:
        version = get_local_poetry_plugin_version(package_name)
        if version:
            return version

    for candidate in candidates:
        version = _query_runtime_version(candidate)
        if version:
            return version

    def _parse_package_show_version(output: str) -> str | None:
        for line in output.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            if key.strip().lower() == "version":
                return value.strip()
        return None

    show_commands = (
        (["poetry", "show", package_name], ["poetry", "self", "show", package_name])
        if package_manager == PackageManager.POETRY
        else (["uv", "pip", "show", package_name],)
    )

    for cmd in show_commands:
        result = utils.run_command(
            list(cmd),
            capture_output=True,
            acceptable_returncodes={0, 1},
        )
        if result.returncode == 0:
            version = _parse_package_show_version(result.stdout)
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


BLACK_TARGET_PYTHON_MINORS = range(7, 17)


def _specifier_supports_python_minor(specifier_set: SpecifierSet, minor: int) -> bool:
    return any(
        specifier_set.contains(Version(f"3.{minor}.{patch}")) for patch in range(1000)
    )


def get_black_target_version() -> str | None:
    """Return the Black target-version token based on `project.requires-python`.

    Returns:
        The lowest supported Python version in Black format, such as
        `py311`, or `None` when the project metadata is missing or invalid.
    """
    requires_python = read_pyproject_toml().get("project", {}).get("requires-python")
    if not isinstance(requires_python, str):
        return None

    try:
        specifier_set = SpecifierSet(requires_python)
    except Exception:
        LOGGER.warning("Unable to parse requires-python specifier: %s", requires_python)
        return None

    for minor in BLACK_TARGET_PYTHON_MINORS:
        if _specifier_supports_python_minor(specifier_set, minor):
            return f"py3{minor:02d}"
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
                "Invalid CUSTOM_ENTRYPOINT value "
                f"{selected_entrypoint!r}. "
                "It must match a key in [project].scripts. "
                f"Available scripts: {', '.join(available_scripts)}"
            )

        utils.fatal(
            "Invalid CUSTOM_ENTRYPOINT value "
            f"{selected_entrypoint!r}. "
            "No [project].scripts entries were found in pyproject.toml."
        )

    script_name = utils.get_package_name(use_underscores=True)
    if script_name in scripts_set:
        return script_name

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
    except Exception:
        return None


def get_project_version() -> str:
    """Return the current project version for release and tagging workflows.

    For Poetry projects, this uses `poetry version` to preserve
    poetry-dynamic-versioning behavior. For uv workflows, it prefers
    `project.version` and falls back to VCS-derived versioning.

    Returns:
        The resolved current project version.
    """
    package_manager = PackageManager(get_package_manager())
    if package_manager == PackageManager.POETRY:
        return get_project_version_from_poetry()

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


def get_release_tag_from_poetry_version() -> str:
    """Return release tag string in `v<version>` form.

    This function is retained for backward compatibility and now uses the
    selected package-manager backend.

    Returns:
        The release tag string prefixed with `v`.
    """
    return get_release_tag_from_project_version()
