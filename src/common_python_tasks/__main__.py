import importlib
import inspect
import os
import re
import sys

from .tasks import tasks

__all__ = ["get_available_tasks", "print_available_tasks"]


def _is_package_task(task_name: str) -> bool:
    task_config = tasks()["tasks"].get(task_name)
    if not isinstance(task_config, dict):
        return False

    script = task_config.get("script")
    if not isinstance(script, str) or ":" not in script:
        return False

    module_name, _ = script.split(":", 1)
    return module_name.startswith("common_python_tasks.")


def get_available_tasks(internal: bool = False) -> list[str]:
    """Return available task names for this package.

    Args:
        internal: If `True`, include internal task names starting with '_'.

    Returns:
        A list of task names.
    """
    return [
        task_name
        for task_name in tasks()["tasks"]
        if _is_package_task(task_name) and (internal or not task_name.startswith("_"))
    ]


def _extract_docstring_excerpt(doc: str) -> str:
    excerpt = []
    for line in doc.strip().splitlines():
        if re.match(r"^(Args?|Arguments?|Parameters?):\s*$", line):
            break
        excerpt.append(line)

    while excerpt and excerpt[-1].strip() == "":
        excerpt.pop()

    return "\n".join(excerpt)


def _get_task_docstring(task_name: str) -> str | None:
    task_config = tasks()["tasks"].get(task_name)
    if not isinstance(task_config, dict):
        return None

    script = task_config.get("script")
    if not isinstance(script, str) or ":" not in script:
        return None

    module_name, func_name = script.split(":", 1)

    try:
        module = importlib.import_module(module_name)
        func = getattr(module, func_name)
    except (ImportError, AttributeError):
        return None

    doc = inspect.getdoc(func)
    if not doc:
        return None

    return _extract_docstring_excerpt(doc)


def get_task_tags(task_name: str) -> list[str] | None:
    """Return the tags associated with a task.

    Args:
        task_name: The name of the task.

    Returns:
        A list of tags associated with the task, or `None` if no tags are found.
    """
    tags = set()
    for task in tasks:
        if task.name != task_name:
            continue

        for tag in task.tags:
            # `task-...` tags are internal synthetic tags auto-added by TaskCollection.
            if not tag.startswith("task-"):
                tags.add(tag)

    return sorted(tags) or None


def print_available_tasks(internal: bool = False, include_docs: bool = False) -> None:
    """Print available tasks.

    Args:
        internal: If `True`, include internal task names starting with '_'.
        include_docs: If `True`, include task docstrings.
    """
    print("\nAvailable tasks in this release:\n")
    for task_name in get_available_tasks(internal=internal):
        print(f" - {task_name}")
        if include_docs:
            doc = _get_task_docstring(task_name)
            if doc:
                for line in doc.splitlines():
                    print(f"     {line}")
                print()


if __name__ == "__main__":
    print(
        "common_python_tasks is not intended to be run as a standalone script. Invoke a task via poethepoet.",
        file=sys.stderr if len(sys.argv) > 1 else sys.stdout,
    )

    if len(sys.argv) == 1:
        debug = os.getenv("COMMON_PYTHON_TASKS_LOG_LEVEL", "info").lower() == "debug"
        print_available_tasks(include_docs=debug)
    else:
        sys.exit(1)
