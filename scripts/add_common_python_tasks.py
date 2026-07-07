#!/usr/bin/env python3

import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

PACKAGE_NAME = "common-python-tasks"
PACKAGE_MANAGER_ENV_VARS = (
    "COMMON_PYTHON_TASKS_PACKAGE_MANAGER",
    "COMMON_PYTHON_TASKS_BUILD_TOOL",
    "PACKAGE_MANAGER",
)
PYPROJECT_PATH = Path("pyproject.toml")
TOOL_POE_PATTERN = re.compile(r"^\s*\[tool\.poe\]\s*(?:#.*)?$")
TABLE_PATTERN = re.compile(r"^\s*\[")
INCLUDE_SCRIPT_PATTERN = re.compile(r"^\s*include_script\s*=")


def _require_command(command: str) -> None:
    if shutil.which(command) is None:
        sys.exit(f"Required command not found: {command}")


def _get_requested_package_manager() -> str:
    for env_var in PACKAGE_MANAGER_ENV_VARS:
        if os.getenv(env_var, "").strip():
            return os.environ[env_var].strip().lower()
    return "auto"


def _select_package_manager() -> str:
    requested_manager = _get_requested_package_manager()
    if requested_manager in {"poetry", "uv"}:
        _require_command(requested_manager)
        return requested_manager
    if requested_manager != "auto":
        sys.exit(f"Unsupported package manager: {requested_manager}")

    for lock_file, package_manager in (
        (Path("uv.lock"), "uv"),
        (Path("poetry.lock"), "poetry"),
    ):
        if lock_file.is_file() and shutil.which(package_manager) is not None:
            return package_manager

    for package_manager in ("uv", "poetry"):
        if shutil.which(package_manager) is not None:
            return package_manager

    sys.exit("Neither uv nor Poetry is installed.")


def _get_package_requirement() -> str:
    if os.getenv("COMMON_PYTHON_TASKS_VERSION", "").strip():
        return f"{PACKAGE_NAME}=={os.environ['COMMON_PYTHON_TASKS_VERSION'].strip()}"
    return PACKAGE_NAME


def _install_package(package_manager: str) -> None:
    if package_manager == "uv":
        command = ["uv", "add", "--dev", _get_package_requirement()]
    else:
        command = ["poetry", "add", "--group", "dev", _get_package_requirement()]
    subprocess.run(command, check=True, shell=False)


def _get_include_script() -> str:
    if os.getenv("TAGS_TO_INCLUDE", "").split():
        return f"common_python_tasks:tasks(include_tags={os.environ['TAGS_TO_INCLUDE'].split()!r})"
    return "common_python_tasks:tasks()"


def _find_tool_poe_section(lines: list[str]) -> tuple[int, int] | None:
    for start_index, line in enumerate(lines):
        if not TOOL_POE_PATTERN.match(line):
            continue
        return start_index, next(
            (
                index
                for index in range(start_index + 1, len(lines))
                if TABLE_PATTERN.match(lines[index])
            ),
            len(lines),
        )
    return None


def _set_include_script(pyproject_text: str, include_script: str) -> str:
    tomllib.loads(pyproject_text)
    lines = pyproject_text.splitlines(keepends=True)
    assignment = f"include_script = {json.dumps(include_script)}\n"
    section = _find_tool_poe_section(lines)
    if section is None:
        return f"{pyproject_text.rstrip()}\n\n[tool.poe]\n{assignment}"

    section_start, section_end = section
    for index in range(section_start + 1, section_end):
        if INCLUDE_SCRIPT_PATTERN.match(lines[index]):
            lines[index] = assignment
            return "".join(lines)

    lines.insert(section_start + 1, assignment)
    return "".join(lines)


def _configure_poe() -> None:
    PYPROJECT_PATH.write_text(
        _set_include_script(
            PYPROJECT_PATH.read_text(encoding="utf-8"),
            _get_include_script(),
        ),
        encoding="utf-8",
    )


def _print_available_tasks() -> None:
    result = subprocess.run(
        ["poe", "--help", "--ansi"],
        check=True,
        capture_output=True,
        shell=False,
        text=True,
    )
    _, marker, configured_tasks = result.stdout.partition("Configured tasks:")
    print(configured_tasks.strip() if marker else result.stdout.strip())


def main() -> None:
    """Install common tasks and configure Poe in the current project."""
    _install_package(_select_package_manager())
    _configure_poe()
    print("\n\033[1;32mCommon Python tasks added to project.\033[0m")
    print("\n\033[1mAvailable tasks:\033[0m")
    _print_available_tasks()


if __name__ == "__main__":
    main()
