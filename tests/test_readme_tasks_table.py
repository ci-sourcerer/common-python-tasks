from pathlib import Path
from unittest.mock import patch

from scripts import readme_tasks_table

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "update_readme_tasks_table.py"
)


def test_build_tasks_table_groups_tasks_by_category():
    task_tags = {
        "format": ["common", "format"],
        "release": ["packaging", "release", "containers"],
        "build-image": ["build", "containers"],
        "stack-up": ["containers", "fastapi", "web"],
    }

    with (
        patch.object(
            readme_tasks_table,
            "get_available_tasks",
            return_value=list(task_tags),
        ),
        patch.object(
            readme_tasks_table,
            "_get_task_docstring",
            side_effect=lambda task_name: f"Run {task_name}",
        ),
        patch.object(readme_tasks_table, "get_task_tags", side_effect=task_tags.get),
    ):
        table = readme_tasks_table.build_tasks_table()

    assert table.index("### Daily development") < table.index(
        "### Packaging and releases"
    )
    assert table.index("### Packaging and releases") < table.index(
        "### Container images"
    )
    assert table.index("### Container images") < table.index("### Development stacks")
    assert table.index("| `release` |") < table.index("### Container images")


def test_replace_tasks_table_updates_existing_block():
    with (
        patch.object(
            readme_tasks_table, "get_available_tasks", return_value=["format"]
        ),
        patch.object(
            readme_tasks_table, "_get_task_docstring", return_value="Format code"
        ),
        patch.object(
            readme_tasks_table,
            "get_task_tags",
            return_value=["common", "format"],
        ),
    ):
        updated_text = readme_tasks_table.replace_tasks_table(
            "Version: 1.2.3\n<!-- tasks-table -->\nold\n<!-- end-tasks-table -->\n"
        )

    assert "Version: 1.2.3" in updated_text
    assert "### Daily development" in updated_text
    assert "| `format` | Format code | common, format |" in updated_text


def test_update_readme_tasks_table_script_main_updates_table_and_commits(
    tmp_path, monkeypatch
):
    readme_path = tmp_path / "README.md"
    readme_path.write_text(
        "Version: 1.2.3\n<!-- tasks-table -->\nold\n<!-- end-tasks-table -->\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)

    from scripts import update_readme_tasks_table as script_module

    with (
        patch.object(
            readme_tasks_table, "get_available_tasks", return_value=["format"]
        ),
        patch.object(
            readme_tasks_table, "_get_task_docstring", return_value="Format code"
        ),
        patch.object(
            readme_tasks_table,
            "get_task_tags",
            return_value=["common", "format"],
        ),
        patch.object(script_module, "commit_readme_update") as mock_commit,
    ):
        script_module.main()

    updated_text = readme_path.read_text(encoding="utf-8")
    assert "### Daily development" in updated_text
    assert "| `format` | Format code | common, format |" in updated_text
    mock_commit.assert_called_once_with("chore(docs): refresh README task table")


def test_update_readme_tasks_table_script_dry_run_leaves_file_unchanged(
    tmp_path, monkeypatch, capsys
):
    readme_path = tmp_path / "README.md"
    original_text = (
        "Version: 1.2.3\n<!-- tasks-table -->\nold\n<!-- end-tasks-table -->\n"
    )
    readme_path.write_text(original_text, encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RELEASE_SCRIPT_DRY_RUN", "1")

    from scripts import update_readme_tasks_table as script_module

    with (
        patch.object(
            readme_tasks_table, "get_available_tasks", return_value=["format"]
        ),
        patch.object(
            readme_tasks_table, "_get_task_docstring", return_value="Format code"
        ),
        patch.object(
            readme_tasks_table,
            "get_task_tags",
            return_value=["common", "format"],
        ),
    ):
        script_module.main()

    assert readme_path.read_text(encoding="utf-8") == original_text
    assert "Would update README.md task table" in capsys.readouterr().err
