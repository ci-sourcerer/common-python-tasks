from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import call, patch

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "release_script.py"
README_PATH = SCRIPT_PATH.parents[1] / "README.md"


def _load_release_script_module():
    spec = spec_from_file_location("release_script_under_test", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load release_script.py for tests")

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_main_pre_phase_replaces_latest_tagged_version_and_rebuilds_table(
    tmp_path, monkeypatch
):
    readme_path = tmp_path / "README.md"
    readme_path.write_text(
        "Version: 1.2.2\n<!-- tasks-table -->\nold\n<!-- end-tasks-table -->\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RELEASE_VERSION", "1.2.3")
    monkeypatch.setenv("RELEASE_SCRIPT_PHASE", "pre")

    release_script = _load_release_script_module()

    with (
        patch.object(release_script, "get_available_tasks", return_value=["format"]),
        patch.object(release_script, "_get_task_docstring", return_value="Format code"),
        patch.object(
            release_script,
            "get_task_tags",
            return_value=["common", "format"],
        ),
        patch.object(
            release_script.subprocess,
            "run",
            side_effect=[
                release_script.subprocess.CompletedProcess(
                    ["git", "tag", "--sort=-version:refname"],
                    0,
                    stdout="v1.2.2\n",
                ),
                None,
                None,
            ],
        ) as mock_run,
    ):
        release_script.main()

    updated_text = readme_path.read_text(encoding="utf-8")
    assert "Version: 1.2.3" in updated_text
    assert "### Daily development" in updated_text
    assert "| `format` | Format code | common, format |" in updated_text
    mock_run.assert_has_calls(
        [
            call(
                ["git", "tag", "--sort=-version:refname"],
                capture_output=True,
                check=True,
                text=True,
            ),
            call(["git", "add", "README.md"], check=True),
            call(
                [
                    "git",
                    "commit",
                    "-m",
                    "chore(release): set README version 1.2.3",
                ],
                check=True,
            ),
        ]
    )


def test_build_tasks_table_groups_tasks_by_category():
    release_script = _load_release_script_module()
    task_tags = {
        "format": ["common", "format"],
        "release": ["packaging", "release", "containers"],
        "build-image": ["build", "containers"],
        "stack-up": ["containers", "fastapi", "web"],
    }

    with (
        patch.object(
            release_script,
            "get_available_tasks",
            return_value=list(task_tags),
        ),
        patch.object(
            release_script,
            "_get_task_docstring",
            side_effect=lambda task_name: f"Run {task_name}",
        ),
        patch.object(release_script, "get_task_tags", side_effect=task_tags.get),
    ):
        table = release_script.build_tasks_table()

    assert table.index("### Daily development") < table.index(
        "### Packaging and releases"
    )
    assert table.index("### Packaging and releases") < table.index(
        "### Container images"
    )
    assert table.index("### Container images") < table.index("### Development stacks")
    assert table.index("| `release` |") < table.index("### Container images")


def test_readme_task_table_matches_generated_table():
    release_script = _load_release_script_module()
    readme_text = README_PATH.read_text(encoding="utf-8")
    table_start = readme_text.index("<!-- tasks-table -->")
    table_end = readme_text.index("<!-- end-tasks-table -->", table_start)

    assert (
        readme_text[table_start : table_end + len("<!-- end-tasks-table -->")]
        == release_script.build_tasks_table()
    )


def test_main_fails_for_invalid_release_phase_without_running_git(
    tmp_path, monkeypatch
):
    readme_path = tmp_path / "README.md"
    readme_path.write_text(
        "Version: 1.2.3\n"
        "<!-- tasks-table -->\n| keep | this | table |\n<!-- end-tasks-table -->\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RELEASE_VERSION", "1.2.3")
    monkeypatch.setenv("RELEASE_SCRIPT_PHASE", "post")

    release_script = _load_release_script_module()

    with (
        patch.object(release_script.subprocess, "run") as mock_run,
        pytest.raises(
            SystemExit,
            match="Invalid 'RELEASE_SCRIPT_PHASE': 'post'. Expected 'pre'.",
        ),
    ):
        release_script.main()

    updated_text = readme_path.read_text(encoding="utf-8")
    assert "Version: 1.2.3" in updated_text
    assert "| keep | this | table |" in updated_text
    mock_run.assert_not_called()


def test_main_dry_run_is_controlled_by_release_script_dry_run_env_pre_phase(
    tmp_path, monkeypatch, capsys
):
    readme_path = tmp_path / "README.md"
    readme_text = (
        "Version: 8.8.8\n<!-- tasks-table -->\nold\n<!-- end-tasks-table -->\n"
    )
    readme_path.write_text(readme_text, encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RELEASE_VERSION", "9.9.9")
    monkeypatch.setenv("RELEASE_SCRIPT_DRY_RUN", "1")
    monkeypatch.setenv("RELEASE_SCRIPT_PHASE", "pre")

    release_script = _load_release_script_module()

    with patch.object(
        release_script.subprocess,
        "run",
        return_value=release_script.subprocess.CompletedProcess(
            ["git", "tag", "--sort=-version:refname"],
            0,
            stdout="v8.8.8\n",
        ),
    ) as mock_run:
        release_script.main()

    assert readme_path.read_text(encoding="utf-8") == readme_text
    output = capsys.readouterr().err
    assert output.startswith("[")
    assert "INFO" in output
    assert "Would modify: README.md" in output
    assert "'8.8.8'" in output
    assert "'9.9.9'" in output
    mock_run.assert_called_once_with(
        ["git", "tag", "--sort=-version:refname"],
        capture_output=True,
        check=True,
        text=True,
    )


def test_main_pre_phase_fails_when_latest_tagged_version_is_missing(
    tmp_path, monkeypatch
):
    readme_path = tmp_path / "README.md"
    readme_path.write_text("Version: 1.2.1\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RELEASE_VERSION", "1.2.3")
    monkeypatch.setenv("RELEASE_SCRIPT_PHASE", "pre")

    release_script = _load_release_script_module()

    with (
        patch.object(
            release_script.subprocess,
            "run",
            return_value=release_script.subprocess.CompletedProcess(
                ["git", "tag", "--sort=-version:refname"],
                0,
                stdout="v1.2.2\n",
            ),
        ),
        pytest.raises(SystemExit, match="latest tagged version"),
    ):
        release_script.main()


def test_main_fails_for_invalid_release_phase_when_release_version_is_missing(
    tmp_path, monkeypatch
):
    readme_path = tmp_path / "README.md"
    readme_path.write_text("Version: 1.2.2\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RELEASE_VERSION", "1.2.3")
    monkeypatch.setenv("RELEASE_SCRIPT_PHASE", "post")

    release_script = _load_release_script_module()

    with (
        patch.object(release_script.subprocess, "run") as mock_run,
        pytest.raises(
            SystemExit,
            match="Invalid 'RELEASE_SCRIPT_PHASE': 'post'. Expected 'pre'.",
        ),
    ):
        release_script.main()

    assert readme_path.read_text(encoding="utf-8") == "Version: 1.2.2\n"
    mock_run.assert_not_called()


def test_release_script_dry_run_env_pre_phase_prints_summary_without_modifying_files(
    tmp_path, monkeypatch, capsys
):
    readme_path = tmp_path / "README.md"
    original_text = "Version: 1.9.9\n"
    readme_path.write_text(original_text, encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RELEASE_VERSION", "2.0.0")
    monkeypatch.setenv("RELEASE_SCRIPT_DRY_RUN", "1")
    monkeypatch.setenv("RELEASE_SCRIPT_PHASE", "pre")

    release_script = _load_release_script_module()

    with patch.object(
        release_script.subprocess,
        "run",
        return_value=release_script.subprocess.CompletedProcess(
            ["git", "tag", "--sort=-version:refname"],
            0,
            stdout="v1.9.9\n",
        ),
    ) as mock_run:
        release_script.main()

    assert readme_path.read_text(encoding="utf-8") == original_text
    output = capsys.readouterr().err
    assert output.startswith("[")
    assert "INFO" in output
    assert "Would modify: README.md" in output
    assert "'1.9.9'" in output
    assert "'2.0.0'" in output
    mock_run.assert_called_once_with(
        ["git", "tag", "--sort=-version:refname"],
        capture_output=True,
        check=True,
        text=True,
    )


def test_release_script_dry_run_env_post_phase_fails_before_git_commands(
    tmp_path, monkeypatch, capsys
):
    readme_path = tmp_path / "README.md"
    original_text = "Version: 2.0.0\n"
    readme_path.write_text(original_text, encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RELEASE_VERSION", "2.0.0")
    monkeypatch.setenv("RELEASE_SCRIPT_DRY_RUN", "1")
    monkeypatch.setenv("RELEASE_SCRIPT_PHASE", "post")

    release_script = _load_release_script_module()

    with (
        patch.object(release_script.subprocess, "run") as mock_run,
        pytest.raises(
            SystemExit,
            match="Invalid 'RELEASE_SCRIPT_PHASE': 'post'. Expected 'pre'.",
        ),
    ):
        release_script.main()

    assert readme_path.read_text(encoding="utf-8") == original_text
    mock_run.assert_not_called()
    assert capsys.readouterr().err == ""
