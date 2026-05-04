#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
from enum import StrEnum, auto
from pathlib import Path

from common_python_tasks.__main__ import (
    _get_task_docstring,
    _get_task_tags,
    get_available_tasks,
)

README_VERSION_PLACEHOLDER = "__RELEASE_VERSION__"
TASKS_TABLE_PATTERN = r"(?ms)<!-- tasks-table -->.*?<!-- end-tasks-table -->"


class ReleasePhase(StrEnum):
    PRE = auto()
    POST = auto()


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


def main(*, phase: ReleasePhase) -> None:
    """Update README placeholder content during pre/post release hooks.

    When the `RELEASE_SCRIPT_DRY_RUN` environment variable is set to `"1"`,
    this function prints what it would modify without making any changes, then
    returns. This implements the release dry-run hook contract: hook scripts
    should check `RELEASE_SCRIPT_DRY_RUN` and self-report their intended
    side effects so the user sees a complete dry-run preview.

    Args:
        phase: Release phase to determine transformation logic.

    Raises:
        SystemExit: If required placeholders are missing or if no changes were made.
    """
    release_version = os.environ["RELEASE_VERSION"]

    if os.environ.get("RELEASE_SCRIPT_DRY_RUN") == "1":
        if phase == ReleasePhase.PRE:
            print(
                f"[DRY RUN] Would modify: README.md "
                f"(replace {README_VERSION_PLACEHOLDER!r} with {release_version!r})"
            )
        else:
            print(
                f"[DRY RUN] Would modify: README.md "
                f"(reset version to {README_VERSION_PLACEHOLDER!r})"
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
    parser = argparse.ArgumentParser(description="Prepare README for release hooks.")
    parser.add_argument(
        "phase",
        choices=[ReleasePhase.PRE.name.lower(), ReleasePhase.POST.name.lower()],
        help="Release phase: 'pre' or 'post'.",
    )
    args = parser.parse_args()
    main(phase=ReleasePhase(args.phase))
