import sys

if __name__ == "__main__":
    print(
        "common_python_tasks is not intended to be run as a standalone script. Invoke a task via poethepoet.",
        file=sys.stderr if len(sys.argv) > 1 else sys.stdout,
    )

    if len(sys.argv) == 1:
        from .tasks import tasks

        print("\nAvailable tasks in this release:\n")
        for task_name in tasks()["tasks"]:
            if task_name.startswith("_"):
                continue
            print(f" - {task_name}")
    else:
        sys.exit(1)