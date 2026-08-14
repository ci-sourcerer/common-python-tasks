import re

from common_python_tasks.__main__ import (
    _get_task_docstring,
    get_available_tasks,
    get_task_tags,
)

TASKS_TABLE_PATTERN = r"(?ms)<!-- tasks-table -->.*?<!-- end-tasks-table -->"
TASK_CATEGORY_ORDER = (
    "Daily development",
    "Packaging and releases",
    "Container images",
    "Development stacks",
)


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


def replace_tasks_table(readme_text: str) -> str:
    """Replace the README task table with the current generated table."""
    return re.sub(TASKS_TABLE_PATTERN, build_tasks_table(), readme_text)
