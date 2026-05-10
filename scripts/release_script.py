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


README_VERSION_PLACEHOLDER = "__RELEASE_VERSION__"
TASKS_TABLE_PATTERN = r"(?ms)<!-- tasks-table -->.*?<!-- end-tasks-table -->"


class ReleasePhase(StrEnum):
    PRE = "pre"
    POST = "post"


RELEASE_SCRIPT_PHASE = "RELEASE_SCRIPT_PHASE"


def _resolve_release_phase(phase: ReleasePhase | None = None) -> ReleasePhase:
    if phase is not None:
        return phase

    phase_value = os.environ.get(RELEASE_SCRIPT_PHASE)
    if phase_value is None:
        raise SystemExit(f"{RELEASE_SCRIPT_PHASE} must be set to 'pre' or 'post'.")

    try:
        return ReleasePhase(phase_value.lower())
    except ValueError as exc:
        raise SystemExit(
            f"Invalid {RELEASE_SCRIPT_PHASE!r}: {phase_value!r}. "
            "Expected 'pre' or 'post'."
        ) from exc


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


def _update_readme_for_pre_release(readme_text: str, release_version: str) -> str:
    if README_VERSION_PLACEHOLDER not in readme_text:
        raise SystemExit(
            "README.md is missing the release placeholder "
            f"{README_VERSION_PLACEHOLDER!r}"
        )

    return re.sub(
        TASKS_TABLE_PATTERN,
        build_tasks_table(),
        readme_text.replace(README_VERSION_PLACEHOLDER, release_version),
    )


def _update_readme_for_post_release(readme_text: str, release_version: str) -> str:
    if release_version not in readme_text:
        raise SystemExit(
            "README.md does not contain the release version "
            f"{release_version!r} to reset"
        )

    return readme_text.replace(release_version, README_VERSION_PLACEHOLDER)


def _commit_readme_update(phase: str, release_version: str) -> None:
    commit_message = (
        f"chore(release): set README version {release_version}"
        if phase == ReleasePhase.PRE
        else "chore(release): reset README version placeholder"
    )

    subprocess.run(["git", "add", "README.md"], check=True)
    subprocess.run(["git", "commit", "-m", commit_message], check=True)


def main(*, phase: ReleasePhase | None = None) -> None:
    """Update README placeholder content during release hook execution.

    The phase is taken from the `RELEASE_SCRIPT_PHASE` environment variable
    when not explicitly provided. When `RELEASE_SCRIPT_DRY_RUN` is set to
    "1", the hook prints the changes it would make without modifying files.

    Args:
        phase: Optional release phase.

    Raises:
        SystemExit: If required placeholders are missing or if no changes were made.
    """
    phase = _resolve_release_phase(phase)
    release_version = os.environ["RELEASE_VERSION"]

    _configure_logger()

    if os.environ.get("RELEASE_SCRIPT_DRY_RUN") == "1":
        if phase == ReleasePhase.PRE:
            log_dry_run(
                "Would modify: README.md " "(replace %r with %r)",
                README_VERSION_PLACEHOLDER,
                release_version,
            )
        else:
            log_dry_run(
                "Would modify: README.md " "(reset version to %r)",
                README_VERSION_PLACEHOLDER,
            )
        return

    readme_path = Path("README.md")
    readme_text = readme_path.read_text(encoding="utf-8")

    updated_text = (
        _update_readme_for_pre_release(readme_text, release_version)
        if phase == ReleasePhase.PRE
        else _update_readme_for_post_release(readme_text, release_version)
    )

    if updated_text == readme_text:
        raise SystemExit("README.md was not changed")

    readme_path.write_text(updated_text, encoding="utf-8")
    _commit_readme_update(phase, release_version)


if __name__ == "__main__":
    main()
