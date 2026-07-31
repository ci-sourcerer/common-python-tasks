#!/usr/bin/env python3

import logging
import os
import re
import subprocess
import sys
from enum import StrEnum
from pathlib import Path

from common_python_tasks.__main__ import (
    _get_task_docstring,
    get_available_tasks,
    get_task_tags,
)


class _ColoredFormatter(logging.Formatter):
    COLORS = {
        "WARNING": "\033[93m",
        "ERROR": "\033[91m",
        "CRITICAL": "\033[91m",
        "RESET": "\033[0m",
    }

    def format(self, record: logging.LogRecord) -> str:
        log_color = self.COLORS.get(record.levelname, "")
        record.levelname = f"\033[1m{log_color}{record.levelname}{self.COLORS['RESET'] if log_color else ''}\033[0m"
        return super().format(record)


LOGGER = logging.getLogger(__name__)
LOGGER.propagate = False
LOGGER.setLevel(logging.INFO)


def _configure_logger() -> None:
    while LOGGER.handlers:
        LOGGER.removeHandler(LOGGER.handlers[0])

    handler = logging.StreamHandler()
    handler.setFormatter(_ColoredFormatter("[%(asctime)s] %(levelname)s: %(message)s"))
    LOGGER.addHandler(handler)


def log_dry_run(message: str, *args: object) -> None:
    """Log a dry-run informational message with a yellow prefix."""
    LOGGER.info("\033[93m[DRY RUN]\033[0m " + message, *args)


TASKS_TABLE_PATTERN = r"(?ms)<!-- tasks-table -->.*?<!-- end-tasks-table -->"
TASK_CATEGORY_ORDER = (
    "Daily development",
    "Packaging and releases",
    "Container images",
    "Development stacks",
)


class ReleasePhase(StrEnum):
    PRE = "pre"


RELEASE_SCRIPT_PHASE = "RELEASE_SCRIPT_PHASE"


def _get_latest_release_version() -> str:
    completed_process = subprocess.run(
        ["git", "tag", "--sort=-version:refname"],
        capture_output=True,
        check=True,
        text=True,
    )
    latest_tag = next(
        (
            line.strip()
            for line in completed_process.stdout.splitlines()
            if line.strip()
        ),
        None,
    )
    if latest_tag is None:
        sys.exit("Unable to determine the latest Git tag for README updates")

    return latest_tag.removeprefix("v")


def _resolve_release_phase(phase: ReleasePhase | None = None) -> ReleasePhase:
    if phase is not None:
        return phase

    phase_value = os.environ.get(RELEASE_SCRIPT_PHASE)
    if phase_value is None:
        sys.exit(f"{RELEASE_SCRIPT_PHASE} must be set to 'pre'.")

    if phase_value.lower() != "pre":
        sys.exit(f"Invalid {RELEASE_SCRIPT_PHASE!r}: {phase_value!r}. Expected 'pre'.")
    return ReleasePhase.PRE


def _get_task_category(task_name: str) -> str:
    tags = get_task_tags(task_name) or []
    if "web" in tags or "database" in tags:
        return "Development stacks"
    if task_name == "release":
        return "Packaging and releases"
    if "containers" in tags:
        return "Container images"
    if "packaging" in tags or "release" in tags:
        return "Packaging and releases"
    return "Daily development"


def _get_task_description(task_name: str) -> str:
    return " ".join(
        line.strip()
        for line in (_get_task_docstring(task_name) or "").splitlines()
        if line.strip()
    )


def build_tasks_table() -> str:
    """Build the markdown task table for README insertion."""
    tasks_by_category = {category: [] for category in TASK_CATEGORY_ORDER}
    for task_name in get_available_tasks(internal=False):
        tasks_by_category[_get_task_category(task_name)].append(task_name)

    lines = ["<!-- tasks-table -->"]
    for category in TASK_CATEGORY_ORDER:
        if not tasks_by_category[category]:
            continue

        lines.extend(
            [
                "",
                f"### {category}",
                "",
                "| Task | Description | Tags |",
                "| --- | --- | --- |",
            ]
        )
        lines.extend(
            f"| `{task_name}` | {_get_task_description(task_name)} | "
            f"{', '.join(get_task_tags(task_name) or [])} |"
            for task_name in tasks_by_category[category]
        )

    lines.extend(["", "<!-- end-tasks-table -->"])
    return "\n".join(lines)


def _update_readme_for_pre_release(
    readme_text: str, current_version: str, release_version: str
) -> str:
    if current_version not in readme_text:
        sys.exit(
            "README.md does not contain the latest tagged version "
            f"{current_version!r} to update"
        )

    return re.sub(
        TASKS_TABLE_PATTERN,
        build_tasks_table(),
        readme_text.replace(current_version, release_version),
    )


def _commit_readme_update(release_version: str) -> None:
    subprocess.run(["git", "add", "README.md"], check=True)
    subprocess.run(
        [
            "git",
            "commit",
            "-m",
            f"chore(release): set README version {release_version}",
        ],
        check=True,
    )


def main() -> None:
    """Update README release content during release hook execution."""
    _resolve_release_phase()
    release_version = os.environ["RELEASE_VERSION"]

    _configure_logger()

    if os.environ.get("RELEASE_SCRIPT_DRY_RUN") == "1":
        current_version = _get_latest_release_version()
        log_dry_run(
            "Would modify: README.md " "(replace %r with %r)",
            current_version,
            release_version,
        )
        return

    readme_path = Path("README.md")
    readme_text = readme_path.read_text(encoding="utf-8")

    updated_text = _update_readme_for_pre_release(
        readme_text,
        _get_latest_release_version(),
        release_version,
    )

    if updated_text == readme_text:
        sys.exit("README.md was not changed")

    readme_path.write_text(updated_text, encoding="utf-8")
    _commit_readme_update(release_version)


if __name__ == "__main__":
    main()
