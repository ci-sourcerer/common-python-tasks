import importlib
import inspect
import re
from pathlib import Path

from common_python_tasks.__main__ import get_available_tasks, get_task_tags
from common_python_tasks.tasks import tasks

TASK_REFERENCE_PATTERN = re.compile(
    r"(?ms)<!-- generated-task-reference -->.*?<!-- end-generated-task-reference -->"
)
DOCKERFILE_REFERENCE_PATTERN = re.compile(
    r"(?ms)<!-- generated-dockerfile-reference -->.*?<!-- end-generated-dockerfile-reference -->"
)
TASK_CATEGORY_FILES = {
    "daily-development": Path("docs/tasks/daily-development.md"),
    "documentation": Path("docs/tasks/documentation.md"),
    "packaging-and-releases": Path("docs/tasks/packaging-and-releases.md"),
    "container-images": Path("docs/tasks/container-images.md"),
    "development-stacks": Path("docs/tasks/development-stacks.md"),
}
DOCKERFILE_REFERENCE_FILE = Path("docs/tasks/container-images.md")
DOCKERFILE_TEMPLATE_FILES = (
    (
        "Application image template",
        Path("src/common_python_tasks/data/generic/Dockerfile.j2"),
    ),
    (
        "Dependency image template",
        Path("src/common_python_tasks/data/generic/Dockerfile.deps.j2"),
    ),
)


def _get_task_category(task_name: str) -> str:
    tags = get_task_tags(task_name) or []
    if "docs" in tags:
        return "documentation"
    if "web" in tags or "database" in tags:
        return "development-stacks"
    if task_name == "release":
        return "packaging-and-releases"
    if "containers" in tags:
        return "container-images"
    if "packaging" in tags or "release" in tags:
        return "packaging-and-releases"
    return "daily-development"


def _get_task_config(task_name: str) -> dict:
    return tasks()["tasks"][task_name]


def _get_docstring_argument_help(task_config: dict) -> dict[str, str]:
    module_name, function_name = task_config["script"].split(":", 1)
    docstring = inspect.getdoc(
        getattr(importlib.import_module(module_name), function_name)
    )
    if not docstring or "\nArgs:\n" not in docstring:
        return {}

    arguments: dict[str, str] = {}
    current_name: str | None = None
    for line in docstring.split("\nArgs:\n", 1)[1].splitlines():
        if line and not line.startswith(" "):
            break
        if match := re.match(r"^\s{4}\*{0,2}([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line):
            current_name = match.group(1)
            arguments[current_name] = match.group(2)
        elif current_name and line.strip():
            arguments[current_name] = f"{arguments[current_name]} {line.strip()}"
    return arguments


def _format_argument_name(argument: dict) -> str:
    if argument.get("positional"):
        suffix = "..." if argument.get("multiple") else ""
        return f"`{argument['name']}{suffix}`"
    return ", ".join(f"`{option}`" for option in argument.get("options", []))


def _format_argument_type(argument: dict) -> str:
    repeatable = ", repeatable" if argument.get("multiple") else ""
    return f"`{argument.get('type', 'string')}{repeatable}`"


def _format_default(argument: dict) -> str:
    if argument.get("required"):
        return "Required"
    if "default" not in argument:
        return "—"
    return f"`{str(argument['default']).lower()}`"


def _format_usage_argument(argument: dict) -> str:
    if argument.get("positional"):
        value = argument["name"].upper()
        if argument.get("multiple"):
            value = f"{value}..."
        return f"<{value}>" if argument.get("required") else f"[{value}]"

    option = argument.get("options", [f"--{argument['name'].replace('_', '-')}"])[0]
    if argument.get("type") != "boolean":
        option = f"{option} {argument['name'].upper()}"
    if argument.get("multiple"):
        option = f"{option}..."
    return option if argument.get("required") else f"[{option}]"


def _escape_table_text(value: str) -> str:
    return value.replace("|", "\\|")


def _render_task_full(task_name: str) -> list[str]:
    task_config = _get_task_config(task_name)
    arguments = task_config.get("args", [])
    lines = [
        f"## `{task_name}`",
        "",
        task_config.get("help", "No description is available."),
        "",
        f"**Tags:** {', '.join(f'`{tag}`' for tag in get_task_tags(task_name) or [])}",
        "",
        "```shell",
        " ".join(
            [f"poe {task_name}", *[_format_usage_argument(arg) for arg in arguments]]
        ),
        "```",
    ]
    if not arguments:
        return lines

    docstring_help = _get_docstring_argument_help(task_config)
    lines.extend(
        [
            "",
            "### Arguments",
            "",
            "| Argument | Type | Description | Default |",
            "| - | - | - | - |",
        ]
    )
    lines.extend(
        "| "
        f"{_format_argument_name(argument)} | "
        f"{_format_argument_type(argument)} | "
        f"{_escape_table_text(argument.get('help') or docstring_help.get(argument['name'], 'Additional value passed to the task.'))} | "
        f"{_format_default(argument)} |"
        for argument in arguments
    )
    return lines


def build_task_reference(category: str) -> str:
    """Build the generated Markdown reference for a task category (link table).

    Args:
        category: Category identifier from `TASK_CATEGORY_FILES`.

    Returns:
        The generated Markdown block with links to individual task pages.

    Raises:
        ValueError: If the category is unknown.
    """
    if category not in TASK_CATEGORY_FILES:
        raise ValueError(f"Unknown task category: {category}")

    task_names = [
        task_name
        for task_name in get_available_tasks()
        if _get_task_category(task_name) == category
    ]

    lines = ["<!-- generated-task-reference -->"]
    if task_names:
        lines.extend(
            [
                "",
                "| Task | Description |",
                "| - | - |",
            ]
        )
        for task_name in task_names:
            task_config = _get_task_config(task_name)
            description = _escape_table_text(
                task_config.get("help", "No description is available.")
            )
            lines.append(
                f"| [`{task_name}`](reference/{task_name}.md) | {description} |"
            )
    lines.extend(["", "<!-- end-generated-task-reference -->"])
    return "\n".join(lines)


def replace_task_reference(text: str, category: str) -> str:
    """Replace a generated task-reference block.

    Args:
        text: Markdown containing the task-reference markers.
        category: Category identifier from `TASK_CATEGORY_FILES`.

    Returns:
        Markdown containing the current generated reference.

    Raises:
        ValueError: If the Markdown does not contain exactly one generated block.
    """
    if len(TASK_REFERENCE_PATTERN.findall(text)) != 1:
        raise ValueError("Expected exactly one generated task-reference block")
    return TASK_REFERENCE_PATTERN.sub(build_task_reference(category), text)


def _build_individual_task_page(task_name: str) -> str:
    """Build the Markdown content for an individual task reference page.

    Args:
        task_name: The task name.

    Returns:
        The complete Markdown content for the task page.
    """
    task_config = _get_task_config(task_name)
    arguments = task_config.get("args", [])
    category = _get_task_category(task_name)

    lines = [
        f"# `poe {task_name}`",
        "",
        task_config.get("help", "No description is available."),
        "",
        f"**Category:** [`{category}`](../{category}.md)",
        "",
        f"**Tags:** {', '.join(f'`{tag}`' for tag in get_task_tags(task_name) or [])}",
        "",
        "## Usage",
        "",
        "```shell",
        " ".join(
            [f"poe {task_name}", *[_format_usage_argument(arg) for arg in arguments]]
        ),
        "```",
    ]

    if arguments:
        docstring_help = _get_docstring_argument_help(task_config)
        lines.extend(
            [
                "",
                "## Arguments",
                "",
                "| Argument | Type | Description | Default |",
                "| - | - | - | - |",
            ]
        )
        lines.extend(
            "| "
            f"{_format_argument_name(argument)} | "
            f"{_format_argument_type(argument)} | "
            f"{_escape_table_text(argument.get('help') or docstring_help.get(argument['name'], 'Additional value passed to the task.'))} | "
            f"{_format_default(argument)} |"
            for argument in arguments
        )

    return "\n".join(lines)


def generate_task_reference_files() -> list[Path]:
    """Generate individual task reference pages in docs/tasks/reference/.

    Returns:
        List of paths to generated files.
    """
    reference_dir = Path("docs/tasks/reference")
    reference_dir.mkdir(parents=True, exist_ok=True)

    generated_files = []
    for task_name in get_available_tasks():
        file_path = reference_dir / f"{task_name}.md"
        content = _build_individual_task_page(task_name)
        file_path.write_text(content, encoding="utf-8")
        generated_files.append(file_path)

    return generated_files


def build_dockerfile_reference() -> str:
    """Build the generated Dockerfile-template documentation block.

    Returns:
        Markdown containing the current bundled Dockerfile templates.
    """
    lines = ["<!-- generated-dockerfile-reference -->"]
    for heading, path in DOCKERFILE_TEMPLATE_FILES:
        lines.extend(
            [
                "",
                f"### {heading}",
                "",
                f"Source: [`{path.name}`](https://github.com/ci-sourcerer/common-python-tasks/blob/main/{path})",
                "",
                "```dockerfile",
                path.read_text(encoding="utf-8").rstrip(),
                "```",
            ]
        )
    lines.extend(["", "<!-- end-generated-dockerfile-reference -->"])
    return "\n".join(lines)


def replace_dockerfile_reference(text: str) -> str:
    """Replace the Dockerfile-template documentation block.

    Args:
        text: Markdown containing the generated Dockerfile-reference markers.

    Returns:
        Markdown containing the current bundled Dockerfile templates.

    Raises:
        ValueError: If the Markdown does not contain exactly one generated block.
    """
    if len(DOCKERFILE_REFERENCE_PATTERN.findall(text)) != 1:
        raise ValueError("Expected exactly one generated Dockerfile-reference block")
    return DOCKERFILE_REFERENCE_PATTERN.sub(build_dockerfile_reference(), text)
