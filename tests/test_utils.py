from unittest.mock import MagicMock, patch

import pytest
from common_python_tasks.utils import (
    fatal,
    get_package_name,
    is_package_installed,
    require_package,
    run_available_tools,
    run_command,
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
