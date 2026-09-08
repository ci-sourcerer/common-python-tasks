import pytest

from scripts.docs_tasks_reference import (
    DOCKERFILE_REFERENCE_FILE,
    TASK_CATEGORY_FILES,
    _build_individual_task_page,
    build_dockerfile_reference,
    build_task_reference,
    replace_dockerfile_reference,
    replace_task_reference,
)


def test_generated_task_reference_is_current():
    for category, path in TASK_CATEGORY_FILES.items():
        current_text = path.read_text(encoding="utf-8")

        assert replace_task_reference(current_text, category) == current_text


def test_generated_dockerfile_reference_is_current():
    current_text = DOCKERFILE_REFERENCE_FILE.read_text(encoding="utf-8")

    assert replace_dockerfile_reference(current_text) == current_text


def test_generated_task_reference_includes_usage_and_arguments():
    reference = build_task_reference("documentation")

    # Category pages now show a link table instead of full task details
    assert "[`docs-build`](reference/docs-build.md)" in reference
    assert "[`docs-serve`](reference/docs-serve.md)" in reference
    assert "Build the Zensical documentation site in strict mode." in reference
    assert "Serve the Zensical documentation site for local preview." in reference


def test_replace_task_reference_requires_one_generated_block():
    with pytest.raises(ValueError, match="exactly one"):
        replace_task_reference("# Documentation\n", "documentation")


def test_dockerfile_reference_includes_template_sources():
    reference = build_dockerfile_reference()

    assert "### Application image template" in reference
    assert "### Dependency image template" in reference
    assert "# syntax=docker/dockerfile:1" in reference


def test_replace_dockerfile_reference_requires_one_generated_block():
    with pytest.raises(ValueError, match="exactly one"):
        replace_dockerfile_reference("# Container images\n")


def test_individual_task_page_includes_usage_and_arguments():
    task_page = _build_individual_task_page("docs-build")

    assert "# `poe docs-build`" in task_page
    assert "**Category:** [`documentation`](../documentation.md)" in task_page
    assert "**Tags:** `docs`" in task_page
    assert "poe docs-build [--config-file CONFIG_FILE] [--clean]" in task_page
    assert "| `--config-file` | `string` |" in task_page
    assert "| `--clean` | `boolean` |" in task_page


def test_individual_task_page_without_arguments():
    task_page = _build_individual_task_page("format")

    assert "# `poe format`" in task_page
    assert "**Category:** [`daily-development`](../daily-development.md)" in task_page
    assert "**Tags:**" in task_page
    assert "`format`" in task_page
    assert "`common`" in task_page
    # Should not have an Arguments section for tasks without args
    assert "## Arguments" not in task_page
