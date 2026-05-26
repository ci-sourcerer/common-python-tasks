from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from common_python_tasks.utils import (
    fatal,
    get_package_name,
    is_package_installed,
    prepend_changelog,
    require_package,
    run_available_tools,
    run_command,
    run_git_cliff,
)


def test_is_package_installed_when_installed(mock_find_spec):
    mock_find_spec.return_value = MagicMock()

    is_package_installed.cache_clear()

    assert is_package_installed("black") is True
    mock_find_spec.assert_called_with("black")


def test_is_package_installed_when_not_installed(mock_find_spec):
    mock_find_spec.return_value = None

    is_package_installed.cache_clear()

    assert is_package_installed("black") is False
    mock_find_spec.assert_called_with("black")


def test_is_package_installed_handles_dashes(mock_find_spec):
    mock_find_spec.return_value = MagicMock()

    is_package_installed.cache_clear()

    assert is_package_installed("pytest-cov") is True
    mock_find_spec.assert_called_with("pytest_cov")


def test_is_package_installed_caches_results(mock_find_spec):
    mock_find_spec.return_value = MagicMock()

    is_package_installed.cache_clear()

    is_package_installed("black")
    is_package_installed("black")

    assert mock_find_spec.call_count == 1


def test_get_package_name_reads_pyproject_when_env_missing(monkeypatch):
    monkeypatch.delenv("PACKAGE_NAME", raising=False)
    get_package_name.cache_clear()
    with patch(
        "common_python_tasks.utils.Path.read_text",
        return_value='[project]\nname = "test-package"\n',
    ):
        assert get_package_name() == "test-package"


def test_run_command_executes_shell_command():
    with patch("common_python_tasks.utils.subprocess.run") as mock_subprocess:
        mock_subprocess.return_value = MagicMock(returncode=0, stdout="")
        run_command(["sh", "-lc", "echo hello"], env={"RELEASE_VERSION": "1.2.3"})

        mock_subprocess.assert_called_once()


def test_run_command_logs_dry_run():
    with patch("common_python_tasks.utils.log_dry_run") as mock_log:
        result = run_command(["sh", "-lc", "echo hello"], dry_run=True)

        assert result is None
        mock_log.assert_called_once_with("Would run command: %s", "sh -lc echo hello")


def test_fatal_logs_and_exits():
    with patch("common_python_tasks.utils.LOGGER") as mock_logger:
        with pytest.raises(SystemExit) as exc_info:
            fatal("Test error message")

        mock_logger.critical.assert_called_once_with("Test error message")
        assert exc_info.value.code == 1


def test_fatal_with_custom_exit_code():
    with patch("common_python_tasks.utils.LOGGER"):
        with pytest.raises(SystemExit) as exc_info:
            fatal("Test error", exit_code=42)

        assert exc_info.value.code == 42


def test_require_package_succeeds_when_installed(mock_find_spec):
    mock_find_spec.return_value = MagicMock()
    is_package_installed.cache_clear()

    require_package("black")


def test_require_package_fails_when_not_installed(mock_find_spec):
    mock_find_spec.return_value = None
    is_package_installed.cache_clear()

    with patch("common_python_tasks.utils.LOGGER"):
        with pytest.raises(SystemExit) as exc_info:
            require_package("black")

        assert exc_info.value.code == 1


def test_run_available_tools_runs_installed_tools(mock_find_spec):
    is_package_installed.cache_clear()

    def find_spec_side_effect(name):
        if name == "black":
            return MagicMock()
        return None

    mock_find_spec.side_effect = find_spec_side_effect

    black_fn = MagicMock()
    isort_fn = MagicMock()

    run_available_tools(
        [(black_fn, "black"), (isort_fn, "isort")], "No tools available"
    )

    black_fn.assert_called_once()
    isort_fn.assert_not_called()


def test_run_available_tools_fails_when_none_installed(mock_find_spec):
    is_package_installed.cache_clear()
    mock_find_spec.return_value = None

    black_fn = MagicMock()
    isort_fn = MagicMock()

    with patch("common_python_tasks.utils.LOGGER"):
        with pytest.raises(SystemExit) as exc_info:
            run_available_tools(
                [(black_fn, "black"), (isort_fn, "isort")], "No tools available"
            )

        assert exc_info.value.code == 1

    black_fn.assert_not_called()
    isort_fn.assert_not_called()


def test_run_available_tools_runs_all_when_all_installed(mock_find_spec):
    is_package_installed.cache_clear()
    mock_find_spec.return_value = MagicMock()

    black_fn = MagicMock()
    isort_fn = MagicMock()
    autoflake_fn = MagicMock()

    run_available_tools(
        [(black_fn, "black"), (isort_fn, "isort"), (autoflake_fn, "autoflake")],
        "No tools available",
    )

    black_fn.assert_called_once()
    isort_fn.assert_called_once()
    autoflake_fn.assert_called_once()


def test_run_git_cliff_passes_args_and_capture_output_to_run_command():
    with (
        patch(
            "common_python_tasks.utils.get_config_path", return_value=Path("cliff.toml")
        ),
        patch("common_python_tasks.utils.run_command") as mock_run_command,
    ):
        mock_run_command.return_value = MagicMock(stdout="notes", returncode=0)

        result = run_git_cliff(["--unreleased"], capture_output=True)

        mock_run_command.assert_called_once_with(
            ["git-cliff", "--config", Path("cliff.toml"), "--unreleased"],
            capture_output=True,
            acceptable_returncodes={0},
        )
        assert result.stdout == "notes"


def test_run_git_cliff_defaults_to_no_capture():
    with (
        patch(
            "common_python_tasks.utils.get_config_path", return_value=Path("cliff.toml")
        ),
        patch("common_python_tasks.utils.run_command") as mock_run_command,
    ):
        run_git_cliff(["--tag", "v1.0.0"])

        mock_run_command.assert_called_once_with(
            ["git-cliff", "--config", Path("cliff.toml"), "--tag", "v1.0.0"],
            capture_output=False,
            acceptable_returncodes={0},
        )


def test_prepend_changelog_creates_scaffold_when_file_missing(tmp_path):
    changelog_path = tmp_path / "CHANGELOG.md"

    with (
        patch(
            "common_python_tasks.utils.get_config_path", return_value=Path("cliff.toml")
        ),
        patch("common_python_tasks.utils.run_command") as mock_run_command,
    ):
        mock_run_command.return_value = MagicMock(stdout="## [1.2.3] - 2026-05-22")
        prepend_changelog("v1.2.3", changelog_path)

    assert changelog_path.read_text(encoding="utf-8") == (
        "## [1.2.3] - 2026-05-22\n\n# Changelog\n\n## [Unreleased]\n"
    )
    mock_run_command.assert_called_once_with(
        [
            "git-cliff",
            "--config",
            Path("cliff.toml"),
            "--unreleased",
            "--tag",
            "v1.2.3",
        ],
        capture_output=True,
        acceptable_returncodes={0},
    )


def test_prepend_changelog_does_not_overwrite_existing_file(tmp_path):
    changelog_path = tmp_path / "CHANGELOG.md"
    changelog_path.write_text("# Existing Changelog\n", encoding="utf-8")

    with (
        patch(
            "common_python_tasks.utils.get_config_path", return_value=Path("cliff.toml")
        ),
        patch("common_python_tasks.utils.run_command") as mock_run_command,
    ):
        mock_run_command.return_value = MagicMock(stdout="## [2.0.0] - 2026-05-22\n")
        prepend_changelog("v2.0.0", changelog_path)

    assert changelog_path.read_text(encoding="utf-8") == (
        "## [2.0.0] - 2026-05-22\n\n# Existing Changelog\n"
    )
    mock_run_command.assert_called_once_with(
        [
            "git-cliff",
            "--config",
            Path("cliff.toml"),
            "--unreleased",
            "--tag",
            "v2.0.0",
        ],
        capture_output=True,
        acceptable_returncodes={0},
    )


def test_prepend_changelog_adds_trailing_newline_to_generated_section(tmp_path):
    changelog_path = tmp_path / "CHANGELOG.md"
    changelog_path.write_text("# Existing Changelog", encoding="utf-8")

    with (
        patch(
            "common_python_tasks.utils.get_config_path", return_value=Path("cliff.toml")
        ),
        patch("common_python_tasks.utils.run_command") as mock_run_command,
    ):
        mock_run_command.return_value = MagicMock(stdout="## [2.0.0] - 2026-05-22")
        prepend_changelog("v2.0.0", changelog_path)

    assert changelog_path.read_text(encoding="utf-8") == (
        "## [2.0.0] - 2026-05-22\n\n# Existing Changelog"
    )
    mock_run_command.assert_called_once_with(
        [
            "git-cliff",
            "--config",
            Path("cliff.toml"),
            "--unreleased",
            "--tag",
            "v2.0.0",
        ],
        capture_output=True,
        acceptable_returncodes={0},
    )


def test_prepend_changelog_uses_changelog_md_as_default_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with (
        patch(
            "common_python_tasks.utils.get_config_path", return_value=Path("cliff.toml")
        ),
        patch("common_python_tasks.utils.run_command") as mock_run_command,
    ):
        mock_run_command.return_value = MagicMock(stdout="## [1.0.0] - 2026-05-22\n")
        prepend_changelog("v1.0.0")

    assert (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8") == (
        "## [1.0.0] - 2026-05-22\n\n# Changelog\n\n## [Unreleased]\n"
    )
    mock_run_command.assert_called_once_with(
        [
            "git-cliff",
            "--config",
            Path("cliff.toml"),
            "--unreleased",
            "--tag",
            "v1.0.0",
        ],
        capture_output=True,
        acceptable_returncodes={0},
    )


def test_render_template_text_injects_extension_content():
    from common_python_tasks.utils import render_template_text

    template = (
        "FROM runtime\n{{ EXTENSION_CONTENT|default('') }}\nFROM runtime AS debug\n"
    )
    rendered = render_template_text(
        template,
        {"EXTENSION_CONTENT": "# ext1\nRUN echo ext1\n"},
    )

    assert "RUN echo ext1" in rendered
    assert rendered.index("RUN echo ext1") < rendered.index("FROM runtime AS debug")
