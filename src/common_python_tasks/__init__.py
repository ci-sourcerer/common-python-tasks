from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

from poethepoet_tasks import TaskCollection

__all__ = ["TaskCollection"]


def tasks(
    include_tags: "Sequence[str] | None" = None,
    exclude_tags: "Sequence[str] | None" = None,
) -> dict:
    """Return the task collection filtered by the requested tags.

    Args:
        include_tags: Tags that selected tasks must have. Defaults to `common`.
        exclude_tags: Tags that selected tasks must not have.

    Returns:
        The filtered Poe task collection configuration.
    """
    from .tasks import tasks as task_collection

    if include_tags is None and not exclude_tags:
        include_tags = ("common",)
    elif include_tags is None:
        include_tags = ()

    if exclude_tags is None:
        exclude_tags = ()

    return task_collection(include_tags=include_tags, exclude_tags=exclude_tags)
