#!/usr/bin/env python3

import logging
import os
import re
import subprocess
from enum import StrEnum
from pathlib import Path

from common_python_tasks.__main__ import (
    _get_task_docstring,
    _get_task_tags,
    get_available_tasks,
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
        raise SystemExit("Unable to determine the latest Git tag for README updates")

    return latest_tag.removeprefix("v")


def _resolve_release_phase(phase: ReleasePhase | None = None) -> ReleasePhase:
    if phase is not None:
        return phase

    phase_value = os.environ.get(RELEASE_SCRIPT_PHASE)
    if phase_value is None:
        raise SystemExit(f"{RELEASE_SCRIPT_PHASE} must be set to 'pre'.")

    if phase_value.lower() != "pre":
        raise SystemExit(
            f"Invalid {RELEASE_SCRIPT_PHASE!r}: {phase_value!r}. Expected 'pre'."
        )
    return ReleasePhase.PRE


def build_tasks_table() -> str:
    """Build the markdown task table for README insertion."""
    lines = [
        "<!-- tasks-table -->",
        "| Task | Description | Tags |",
        "| - | - | - |",
    ]

    for task_name in get_available_tasks(internal=False):
        doc = _get_task_docstring(task_name) or ""
        description = " ".join(doc.splitlines()).strip()
        tags = _get_task_tags(task_name) or []
        lines.append(f"| `{task_name}` | {description} | {', '.join(tags)} |")

    lines.append("<!-- end-tasks-table -->")
    return "\n".join(lines)


def _update_readme_for_pre_release(
    readme_text: str, current_version: str, release_version: str
) -> str:
    if current_version not in readme_text:
        raise SystemExit(
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
        raise SystemExit("README.md was not changed")

    readme_path.write_text(updated_text, encoding="utf-8")
    _commit_readme_update(release_version)


if __name__ == "__main__":
    main()
