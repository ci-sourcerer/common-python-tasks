#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
from pathlib import Path

from common_python_tasks.__main__ import (
    _get_task_docstring,
    _get_task_tags,
    get_available_tasks,
)


def run_command(command: list[str]) -> str:
    return subprocess.run(
        command, capture_output=True, text=True, check=True
    ).stdout.strip()


def get_latest_git_tag() -> str:
    return run_command(["git", "describe", "--tags", "--abbrev=0"])


def build_tasks_table() -> str:
    lines = [
        "<!-- tasks-table -->",
        "| Task | Description | Tags |",
        "| - | - | - |",
    ]

    for task_name in get_available_tasks(internal=False):
        doc = _get_task_docstring(task_name) or ""
        description = " ".join(doc.splitlines()).strip()
        tags = _get_task_tags(task_name) or []
        tags_value = ", ".join(tags)
        lines.append(f"| `{task_name}` | {description} | {tags_value} |")

    lines.append("<!-- end-tasks-table -->")
    return "\n".join(lines)


def main(dry_run: bool = False) -> None:
    release_version = os.environ["RELEASE_VERSION"]
    last_tag = get_latest_git_tag()
    last_tag_no_v = last_tag.removeprefix("v")

    readme_path = Path("README.md")
    readme_text = readme_path.read_text(encoding="utf-8")

    updated_text = readme_text.replace(last_tag_no_v, release_version)
    updated_text = re.sub(
        r"(?ms)<!-- tasks-table -->.*?<!-- end-tasks-table -->",
        build_tasks_table(),
        updated_text,
    )

    if updated_text == readme_text:
        raise SystemExit("README.md was not changed")

    if dry_run:
        print(updated_text)
        return

    readme_path.write_text(updated_text, encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], check=True)
    subprocess.run(
        [
            "git",
            "commit",
            "-m",
            f"chore: update README.md for release {release_version}",
        ],
        check=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare README for release.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the updated README content instead of writing it.",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)
