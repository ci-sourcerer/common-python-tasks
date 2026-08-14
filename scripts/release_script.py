#!/usr/bin/env python3

import os
import subprocess
import sys
from enum import StrEnum
from pathlib import Path

from utils import commit_readme_update, configure_logger, get_logger, log_dry_run

from common_python_tasks.readme_tasks_table import replace_tasks_table

LOGGER = get_logger(__name__)


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


def _update_readme_for_pre_release(
    readme_text: str, current_version: str, release_version: str
) -> str:
    if current_version not in readme_text:
        sys.exit(
            "README.md does not contain the latest tagged version "
            f"{current_version!r} to update"
        )

    return replace_tasks_table(readme_text.replace(current_version, release_version))


def main() -> None:
    """Update README release content during release hook execution."""
    _resolve_release_phase()
    release_version = os.environ["RELEASE_VERSION"]

    configure_logger(LOGGER)

    if os.environ.get("RELEASE_SCRIPT_DRY_RUN") == "1":
        current_version = _get_latest_release_version()
        log_dry_run(
            LOGGER,
            "Would modify: README.md (replace %r with %r)",
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
    commit_readme_update(f"chore(release): set README version {release_version}")


if __name__ == "__main__":
    main()
