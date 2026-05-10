from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import call, patch

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "release_script.py"


def _load_release_script_module():
    spec = spec_from_file_location("release_script_under_test", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load release_script.py for tests")

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_main_pre_phase_replaces_placeholder_and_rebuilds_table(tmp_path, monkeypatch):
    readme_path = tmp_path / "README.md"
    readme_path.write_text(
        "Version: __RELEASE_VERSION__\n"
        "<!-- tasks-table -->\nold\n<!-- end-tasks-table -->\n",
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
            "_get_task_tags",
            return_value=["common", "format"],
        ),
        patch.object(release_script.subprocess, "run") as mock_run,
    ):
        release_script.main()

    updated_text = readme_path.read_text(encoding="utf-8")
    assert "__RELEASE_VERSION__" not in updated_text
    assert "Version: 1.2.3" in updated_text
    assert "| `format` | Format code | common, format |" in updated_text
    mock_run.assert_has_calls(
        [
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


def test_main_post_phase_restores_placeholder_without_rebuilding_table(
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

    with patch.object(release_script.subprocess, "run") as mock_run:
        release_script.main()

    updated_text = readme_path.read_text(encoding="utf-8")
    assert "Version: __RELEASE_VERSION__" in updated_text
    assert "| keep | this | table |" in updated_text
    mock_run.assert_has_calls(
        [
            call(["git", "add", "README.md"], check=True),
            call(
                [
                    "git",
                    "commit",
                    "-m",
                    "chore(release): reset README version placeholder",
                ],
                check=True,
            ),
        ]
    )


def test_main_dry_run_is_controlled_by_release_script_dry_run_env_pre_phase(
    tmp_path, monkeypatch, capsys
):
    readme_path = tmp_path / "README.md"
    readme_text = (
        "Version: __RELEASE_VERSION__\n"
        "<!-- tasks-table -->\nold\n<!-- end-tasks-table -->\n"
    )
    readme_path.write_text(readme_text, encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RELEASE_VERSION", "9.9.9")
    monkeypatch.setenv("RELEASE_SCRIPT_DRY_RUN", "1")
    monkeypatch.setenv("RELEASE_SCRIPT_PHASE", "pre")

    release_script = _load_release_script_module()

    with patch.object(release_script.subprocess, "run") as mock_run:
        release_script.main()

    assert readme_path.read_text(encoding="utf-8") == readme_text
    output = capsys.readouterr().err
    assert output.startswith("[")
    assert "INFO: [DRY RUN] Would modify: README.md" in output
    assert "'__RELEASE_VERSION__'" in output
    assert "'9.9.9'" in output
    mock_run.assert_not_called()


def test_main_pre_phase_fails_when_placeholder_is_missing(tmp_path, monkeypatch):
    readme_path = tmp_path / "README.md"
    readme_path.write_text("Version: 1.2.2\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RELEASE_VERSION", "1.2.3")
    monkeypatch.setenv("RELEASE_SCRIPT_PHASE", "pre")

    release_script = _load_release_script_module()

    with pytest.raises(SystemExit, match="release placeholder"):
        release_script.main()


def test_main_post_phase_fails_when_release_version_is_missing(tmp_path, monkeypatch):
    readme_path = tmp_path / "README.md"
    readme_path.write_text("Version: __RELEASE_VERSION__\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RELEASE_VERSION", "1.2.3")
    monkeypatch.setenv("RELEASE_SCRIPT_PHASE", "post")

    release_script = _load_release_script_module()

    with pytest.raises(SystemExit, match="does not contain the release version"):
        release_script.main()


def test_release_script_dry_run_env_pre_phase_prints_summary_without_modifying_files(
    tmp_path, monkeypatch, capsys
):
    readme_path = tmp_path / "README.md"
    original_text = "Version: __RELEASE_VERSION__\n"
    readme_path.write_text(original_text, encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RELEASE_VERSION", "2.0.0")
    monkeypatch.setenv("RELEASE_SCRIPT_DRY_RUN", "1")
    monkeypatch.setenv("RELEASE_SCRIPT_PHASE", "pre")

    release_script = _load_release_script_module()

    with patch.object(release_script.subprocess, "run") as mock_run:
        release_script.main()

    assert readme_path.read_text(encoding="utf-8") == original_text
    mock_run.assert_not_called()
    output = capsys.readouterr().err
    assert output.startswith("[")
    assert "INFO: [DRY RUN] Would modify: README.md" in output
    assert "'__RELEASE_VERSION__'" in output
    assert "'2.0.0'" in output


def test_release_script_dry_run_env_post_phase_prints_summary_without_modifying_files(
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

    with patch.object(release_script.subprocess, "run") as mock_run:
        release_script.main()

    assert readme_path.read_text(encoding="utf-8") == original_text
    mock_run.assert_not_called()
    output = capsys.readouterr().err
    assert output.startswith("[")
    assert "INFO: [DRY RUN] Would modify: README.md" in output
    assert "'__RELEASE_VERSION__'" in output
