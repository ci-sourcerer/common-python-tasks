import contextvars
import inspect
import logging
import os
import shlex
from collections.abc import Callable
from functools import partial, wraps
from pathlib import Path
from typing import ClassVar

from poethepoet_tasks import TaskCollection


class _ColoredFormatter(logging.Formatter):
    COLORS: ClassVar = {
        "WARNING": "\033[93m",
        "ERROR": "\033[91m",
        "CRITICAL": "\033[91m",
        "RESET": "\033[0m",
    }

    def format(self, record: logging.LogRecord) -> str:
        log_color = self.COLORS.get(record.levelname, "")
        record.levelname = f"\033[1m{log_color}{record.levelname}{self.COLORS['RESET'] if log_color else ''}\033[0m"
        return super().format(record)


LOGGER = logging.getLogger("common_python_tasks")
handler = logging.StreamHandler()
handler.setFormatter(_ColoredFormatter("[%(asctime)s] %(levelname)s: %(message)s"))
LOGGER.addHandler(handler)
LOGGER.setLevel(
    {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }[os.getenv("COMMON_PYTHON_TASKS_LOG_LEVEL", "INFO").upper()]
)


tasks = TaskCollection(
    envfile=[
        f
        for f in [
            ".env.defaults",
            "project.properties",
            ".env",
        ]
        if Path(f).exists()
    ]
)

_task_call_depth: contextvars.ContextVar[int] = contextvars.ContextVar(
    "common_python_tasks_task_call_depth", default=0
)

_original_script = tasks.script


def _make_var_positional_task_args_optional(
    func: callable, resolved_task_name: str
) -> None:
    var_positional_arg_names = {
        param.name
        for param in inspect.signature(func).parameters.values()
        if param.kind == inspect.Parameter.VAR_POSITIONAL
    }
    if not var_positional_arg_names:
        return

    for task_config in tasks._tasks.get(resolved_task_name, []):
        for arg_config in task_config.options.get("args", []):
            if arg_config.get("name") in var_positional_arg_names:
                arg_config["required"] = False


def _wrap_task_function(func: callable, task_name: str | None) -> callable:
    resolved_task_name = task_name or func.__name__.replace("_", "-").lower()
    var_positional_arg_names = [
        param.name
        for param in inspect.signature(func).parameters.values()
        if param.kind == inspect.Parameter.VAR_POSITIONAL
    ]

    @wraps(func)
    def wrapped(*args, **kwargs):
        for arg_name in var_positional_arg_names:
            if arg_name not in kwargs:
                continue
            values = kwargs.pop(arg_name)
            if values is None:
                continue
            if isinstance(values, list | tuple):
                args = (*args, *values)
            else:
                args = (*args, values)

        if var_positional_arg_names and (
            poe_extra_args := os.environ.pop("POE_EXTRA_ARGS", None)
        ):
            args = (*args, *shlex.split(poe_extra_args))

        current_depth = _task_call_depth.get()
        if current_depth > 0:
            LOGGER.log(
                (
                    logging.INFO
                    if not resolved_task_name.startswith("_")
                    else logging.DEBUG
                ),
                "Running task %s",
                resolved_task_name,
            )
        token = _task_call_depth.set(current_depth + 1)
        try:
            return func(*args, **kwargs)
        finally:
            _task_call_depth.reset(token)

    return wrapped


def _script(
    func: Callable | None = None,
    task_name: str | None = None,
    help: str | None = None,
    task_args: bool = True,
    options: dict | None = None,
    tags: tuple[str, ...] | None = None,
):

    if tags is None:
        tags = ()

    if func is None:
        return partial(
            _script,
            task_name=task_name,
            help=help,
            task_args=task_args,
            options=options,
            tags=tags,
        )

    resolved_task_name = task_name or func.__name__.replace("_", "-").lower()
    wrapped = _wrap_task_function(func, resolved_task_name)
    decorated = _original_script(
        wrapped,
        task_name=resolved_task_name,
        help=help,
        task_args=task_args,
        options=options,
        tags=tags,
    )
    _make_var_positional_task_args_optional(wrapped, resolved_task_name)
    return decorated


tasks.script = _script

NO_PROMPT_ENV_VAR = "COMMON_PYTHON_TASKS_NO_PROMPT"
