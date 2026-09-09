from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import release_script

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "release_script.py"


def test_main_pre_phase_replaces_latest_tagged_version(tmp_path, monkeypatch):
    readme_path = tmp_path / "README.md"
    readme_path.write_text("Version: 1.2.2\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RELEASE_VERSION", "1.2.3")
    monkeypatch.setenv("RELEASE_SCRIPT_PHASE", "pre")

    with (
        patch.object(
            release_script.subprocess,
            "run",
            side_effect=[
                release_script.subprocess.CompletedProcess(
                    ["git", "tag", "--sort=-version:refname"],
                    0,
                    stdout="v1.2.2\n",
                ),
            ],
        ) as mock_run,
        patch.object(release_script, "commit_readme_update") as mock_commit,
    ):
        release_script.main()

    updated_text = readme_path.read_text(encoding="utf-8")
    assert "Version: 1.2.3" in updated_text
    mock_run.assert_called_once_with(
        ["git", "tag", "--sort=-version:refname"],
        capture_output=True,
        check=True,
        text=True,
    )
    mock_commit.assert_called_once_with("chore(release): set README version 1.2.3")


def test_main_fails_for_invalid_release_phase_without_running_git(
    tmp_path, monkeypatch
):
    readme_path = tmp_path / "README.md"
    readme_path.write_text("Version: 1.2.3\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RELEASE_VERSION", "1.2.3")
    monkeypatch.setenv("RELEASE_SCRIPT_PHASE", "post")

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
    mock_run.assert_not_called()


def test_main_dry_run_is_controlled_by_release_script_dry_run_env_pre_phase(
    tmp_path, monkeypatch, capsys
):
    readme_path = tmp_path / "README.md"
    readme_text = "Version: 8.8.8\n"
    readme_path.write_text(readme_text, encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RELEASE_VERSION", "9.9.9")
    monkeypatch.setenv("RELEASE_SCRIPT_DRY_RUN", "1")
    monkeypatch.setenv("RELEASE_SCRIPT_PHASE", "pre")

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
