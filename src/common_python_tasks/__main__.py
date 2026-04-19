import sys

__all__ = ["get_available_tasks"]


def get_available_tasks(internal: bool = False) -> list[str]:
    """Return available task names for this package.

    Args:
        internal: When True, include internal task names starting with '_'.

    Returns:
        A list of task names.
    """
    from .tasks import tasks

    return [
        task_name
        for task_name in tasks()["tasks"]
        if internal or not task_name.startswith("_")
    ]


if __name__ == "__main__":
    print(
        "common_python_tasks is not intended to be run as a standalone script. Invoke a task via poethepoet.",
        file=sys.stderr if len(sys.argv) > 1 else sys.stdout,
    )

    if len(sys.argv) == 1:
        print("\nAvailable tasks in this release:\n")
        for task_name in get_available_tasks():
            print(f" - {task_name}")
    else:
        sys.exit(1)
