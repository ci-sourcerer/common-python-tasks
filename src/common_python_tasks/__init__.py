from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

from poethepoet_tasks import TaskCollection

__version__ = "0.0.0"

__all__ = ["TaskCollection"]


def tasks(
    include_tags: "Sequence[str]" = tuple(), exclude_tags: "Sequence[str]" = tuple()
):
    from .tasks import tasks

    return tasks(include_tags=include_tags, exclude_tags=exclude_tags)
