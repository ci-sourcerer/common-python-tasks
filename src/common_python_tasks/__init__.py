from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Sequence

from poethepoet_tasks import TaskCollection

__all__ = ["TaskCollection"]


def tasks(
    include_tags: "Sequence[str] | None" = None,
    exclude_tags: "Sequence[str]" = tuple(),
) -> dict:
    from .tasks import tasks as task_collection

    if include_tags is None and not exclude_tags:
        include_tags = ("common",)
    elif include_tags is None:
        include_tags = tuple()

    result = task_collection(include_tags=include_tags, exclude_tags=exclude_tags)
    globals()["tasks"] = _TASKS_ENTRYPOINT
    return result


_TASKS_ENTRYPOINT = tasks
