from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_find_spec():
    """Mock importlib.util.find_spec for package availability testing."""
    with patch("importlib.util.find_spec") as mock:
        yield mock


def test_is_package_installed_when_installed(mock_find_spec):
    """Test _is_package_installed returns True when package is found."""
    from common_python_tasks.tasks import _is_package_installed

    mock_find_spec.return_value = MagicMock()

    _is_package_installed.cache_clear()

    assert _is_package_installed("black") is True
    mock_find_spec.assert_called_with("black")


def test_is_package_installed_when_not_installed(mock_find_spec):
    """Test _is_package_installed returns False when package is not found."""
    from common_python_tasks.tasks import _is_package_installed

    mock_find_spec.return_value = None

    _is_package_installed.cache_clear()

    assert _is_package_installed("black") is False
    mock_find_spec.assert_called_with("black")


def test_is_package_installed_handles_dashes(mock_find_spec):
    """Test _is_package_installed converts dashes to underscores."""
    from common_python_tasks.tasks import _is_package_installed

    mock_find_spec.return_value = MagicMock()

    _is_package_installed.cache_clear()

    assert _is_package_installed("pytest-cov") is True
    mock_find_spec.assert_called_with("pytest_cov")


def test_is_package_installed_caches_results(mock_find_spec):
    """Test _is_package_installed caches results."""
    from common_python_tasks.tasks import _is_package_installed

    mock_find_spec.return_value = MagicMock()

    _is_package_installed.cache_clear()

    _is_package_installed("black")
    _is_package_installed("black")

    assert mock_find_spec.call_count == 1


def test_fatal_logs_and_exits():
    """Test _fatal logs error and exits with correct code."""
    from common_python_tasks.tasks import _fatal

    with patch("common_python_tasks.tasks.LOGGER") as mock_logger:
        with pytest.raises(SystemExit) as exc_info:
            _fatal("Test error message")

        mock_logger.critical.assert_called_once_with("Test error message")
        assert exc_info.value.code == 1


def test_fatal_with_custom_exit_code():
    """Test _fatal uses custom exit code."""
    from common_python_tasks.tasks import _fatal

    with patch("common_python_tasks.tasks.LOGGER"):
        with pytest.raises(SystemExit) as exc_info:
            _fatal("Test error", exit_code=42)

        assert exc_info.value.code == 42


def test_require_package_succeeds_when_installed(mock_find_spec):
    """Test _require_package succeeds when package is installed."""
    from common_python_tasks.tasks import _is_package_installed, _require_package

    mock_find_spec.return_value = MagicMock()
    _is_package_installed.cache_clear()

    _require_package("black")


def test_require_package_fails_when_not_installed(mock_find_spec):
    """Test _require_package exits when package is not installed."""
    from common_python_tasks.tasks import _is_package_installed, _require_package

    mock_find_spec.return_value = None
    _is_package_installed.cache_clear()

    with patch("common_python_tasks.tasks.LOGGER"):
        with pytest.raises(SystemExit) as exc_info:
            _require_package("black")

        assert exc_info.value.code == 1


def test_run_available_tools_runs_installed_tools(mock_find_spec):
    """Test _run_available_tools runs only installed tools."""
    from common_python_tasks.tasks import _is_package_installed, _run_available_tools

    _is_package_installed.cache_clear()

    def find_spec_side_effect(name):
        if name == "black":
            return MagicMock()
        return None

    mock_find_spec.side_effect = find_spec_side_effect

    black_fn = MagicMock()
    isort_fn = MagicMock()

    _run_available_tools(
        [(black_fn, "black"), (isort_fn, "isort")], "No tools available"
    )

    black_fn.assert_called_once()
    isort_fn.assert_not_called()


def test_run_available_tools_fails_when_none_installed(mock_find_spec):
    """Test _run_available_tools exits when no tools are installed."""
    from common_python_tasks.tasks import _is_package_installed, _run_available_tools

    _is_package_installed.cache_clear()
    mock_find_spec.return_value = None

    black_fn = MagicMock()
    isort_fn = MagicMock()

    with patch("common_python_tasks.tasks.LOGGER"):
        with pytest.raises(SystemExit) as exc_info:
            _run_available_tools(
                [(black_fn, "black"), (isort_fn, "isort")], "No tools available"
            )

        assert exc_info.value.code == 1

    black_fn.assert_not_called()
    isort_fn.assert_not_called()


def test_run_available_tools_runs_all_when_all_installed(mock_find_spec):
    """Test _run_available_tools runs all tools when all are installed."""
    from common_python_tasks.tasks import _is_package_installed, _run_available_tools

    _is_package_installed.cache_clear()
    mock_find_spec.return_value = MagicMock()

    black_fn = MagicMock()
    isort_fn = MagicMock()
    autoflake_fn = MagicMock()

    _run_available_tools(
        [(black_fn, "black"), (isort_fn, "isort"), (autoflake_fn, "autoflake")],
        "No tools available",
    )

    black_fn.assert_called_once()
    isort_fn.assert_called_once()
    autoflake_fn.assert_called_once()


def test_format_all_uses_run_available_tools(mock_find_spec):
    """Test format_all task uses _run_available_tools correctly."""
    from common_python_tasks.tasks import _is_package_installed, format_all

    _is_package_installed.cache_clear()
    mock_find_spec.return_value = MagicMock()

    with patch("common_python_tasks.tasks._run_command") as mock_cmd:
        format_all()

        assert mock_cmd.call_count == 3


def test_lint_all_uses_run_available_tools(mock_find_spec):
    """Test lint_all task uses _run_available_tools correctly."""
    from common_python_tasks.tasks import _is_package_installed, lint_all

    _is_package_installed.cache_clear()
    mock_find_spec.return_value = MagicMock()

    with patch("common_python_tasks.tasks._run_command") as mock_cmd:
        with patch("common_python_tasks.tasks.get_config_path") as mock_config:
            mock_config.return_value = ".flake8"
            lint_all()

        assert mock_cmd.call_count == 4


def test_format_all_fails_when_no_tools_installed(mock_find_spec):
    """Test format_all exits when no formatting tools are installed."""
    from common_python_tasks.tasks import _is_package_installed, format_all

    _is_package_installed.cache_clear()
    mock_find_spec.return_value = None

    with patch("common_python_tasks.tasks.LOGGER"):
        with pytest.raises(SystemExit) as exc_info:
            format_all()

        assert exc_info.value.code == 1


def test_lint_all_fails_when_no_tools_installed(mock_find_spec):
    """Test lint_all exits when no linting tools are installed."""
    from common_python_tasks.tasks import _is_package_installed, lint_all

    _is_package_installed.cache_clear()
    mock_find_spec.return_value = None

    with patch("common_python_tasks.tasks.LOGGER"):
        with pytest.raises(SystemExit) as exc_info:
            lint_all()

        assert exc_info.value.code == 1


class TestHasTagsLaterInHistory:
    """Tests for checking if there are tags later in git history."""

    def test_no_tags_exist(self):
        """Test when no tags exist in the repository."""
        from common_python_tasks.tasks import _has_tags_later_in_history

        with patch("common_python_tasks.tasks._run_command") as mock:

            def side_effect(command, *args, **kwargs):
                result = MagicMock()
                if command == ["git", "tag"]:
                    result.returncode = 0
                    result.stdout = ""
                return result

            mock.side_effect = side_effect

            assert not _has_tags_later_in_history()

    def test_no_tags_later_in_history(self):
        """Test when all tags are ancestors of current HEAD."""
        from common_python_tasks.tasks import _has_tags_later_in_history

        with patch("common_python_tasks.tasks._run_command") as mock:

            def side_effect(command, *args, **kwargs):
                result = MagicMock()
                if command == ["git", "tag"]:
                    result.returncode = 0
                    result.stdout = "v1.0.0\nv1.1.0\nv1.2.0"
                elif command[:3] == ["git", "merge-base", "--is-ancestor"]:
                    result.returncode = 0
                else:
                    result.returncode = 0
                    result.stdout = ""
                return result

            mock.side_effect = side_effect

            assert not _has_tags_later_in_history()

    def test_has_tags_later_in_history(self):
        """Test when there are tags not reachable from current HEAD."""
        from common_python_tasks.tasks import _has_tags_later_in_history

        with patch("common_python_tasks.tasks._run_command") as mock:
            call_count = 0

            def side_effect(command, *args, **kwargs):
                nonlocal call_count
                result = MagicMock()
                if command == ["git", "tag"]:
                    result.returncode = 0
                    result.stdout = "v1.0.0\nv1.1.0\nv2.0.0"
                elif command[:3] == ["git", "merge-base", "--is-ancestor"]:
                    call_count += 1
                    if call_count <= 2:
                        result.returncode = 0
                    else:
                        result.returncode = 1
                else:
                    result.returncode = 0
                    result.stdout = ""
                return result

            mock.side_effect = side_effect

            assert _has_tags_later_in_history()

    def test_git_tag_command_fails(self):
        """Test when git tag command fails."""
        from common_python_tasks.tasks import _has_tags_later_in_history

        with patch("common_python_tasks.tasks._run_command") as mock:

            def side_effect(command, *args, **kwargs):
                result = MagicMock()
                if command == ["git", "tag"]:
                    result.returncode = 128
                    result.stdout = ""
                return result

            mock.side_effect = side_effect

            assert not _has_tags_later_in_history()


class TestBumpVersion:
    """Tests for version bumping functionality."""

    @pytest.fixture
    def tag_calls(self):
        """Collect git tag arguments issued by bump_version."""
        return []

    @pytest.fixture
    def mock_clean_repo_no_tags(self, tag_calls):
        """Mock clean repository with no existing tags."""
        with patch("common_python_tasks.tasks._get_dirty_files") as mock_dirty:
            with patch("common_python_tasks.tasks._run_command") as mock_run:
                mock_dirty.return_value = []  # Clean repo

                def side_effect(command, *args, **kwargs):
                    result = MagicMock()
                    if command[:4] == ["git", "describe", "--tags", "--abbrev=0"]:
                        result.returncode = 128
                        result.stdout = ""
                    elif (
                        len(command) >= 3
                        and command[0] == "git"
                        and command[1] == "tag"
                    ):
                        result.returncode = 0
                        tag_calls.append(command[-1])
                        result.stdout = ""
                    else:
                        result.returncode = 0
                        result.stdout = ""
                    return result

                mock_run.side_effect = side_effect
                yield mock_run

    @pytest.fixture
    def mock_clean_repo_with_tag(self, tag_calls):
        """Mock clean repository with existing v1.2.3 tag."""
        with patch("common_python_tasks.tasks._get_dirty_files") as mock_dirty:
            with patch("common_python_tasks.tasks._run_command") as mock_run:
                mock_dirty.return_value = []  # Clean repo

                def side_effect(command, *args, **kwargs):
                    result = MagicMock()
                    if command[:4] == ["git", "describe", "--tags", "--abbrev=0"]:
                        result.returncode = 0
                        result.stdout = "v1.2.3"
                    elif (
                        len(command) >= 3
                        and command[0] == "git"
                        and command[1] == "tag"
                    ):
                        result.returncode = 0
                        tag_calls.append(command[-1])
                        result.stdout = ""
                    else:
                        result.returncode = 0
                        result.stdout = ""
                    return result

                mock_run.side_effect = side_effect
                yield mock_run

    def test_bump_major_no_tags(self, mock_clean_repo_no_tags, tag_calls):
        from common_python_tasks.tasks import bump_version

        bump_version("major")
        assert tag_calls[-1] == "v1.0.0"

    def test_bump_minor_no_tags(self, mock_clean_repo_no_tags, tag_calls):
        from common_python_tasks.tasks import bump_version

        bump_version("minor")
        assert tag_calls[-1] == "v0.1.0"

    def test_bump_patch_no_tags(self, mock_clean_repo_no_tags, tag_calls):
        from common_python_tasks.tasks import bump_version

        bump_version("patch")
        assert tag_calls[-1] == "v0.0.1"

    def test_bump_major_with_existing_tag(self, mock_clean_repo_with_tag, tag_calls):
        from common_python_tasks.tasks import bump_version

        bump_version("major")
        assert tag_calls[-1] == "v2.0.0"

    def test_bump_minor_with_existing_tag(self, mock_clean_repo_with_tag, tag_calls):
        from common_python_tasks.tasks import bump_version

        bump_version("minor")
        assert tag_calls[-1] == "v1.3.0"

    def test_bump_patch_with_existing_tag(self, mock_clean_repo_with_tag, tag_calls):
        from common_python_tasks.tasks import bump_version

        bump_version("patch")
        assert tag_calls[-1] == "v1.2.4"

    def test_bump_with_alpha_stage(self, mock_clean_repo_with_tag, tag_calls):
        from common_python_tasks.tasks import bump_version

        bump_version("patch", stage="alpha")
        assert tag_calls[-1] == "v1.2.4a1"

    def test_bump_with_beta_stage(self, mock_clean_repo_with_tag, tag_calls):
        from common_python_tasks.tasks import bump_version

        bump_version("minor", stage="beta")
        assert tag_calls[-1] == "v1.3.0b1"

    def test_bump_with_rc_stage(self, mock_clean_repo_with_tag, tag_calls):
        from common_python_tasks.tasks import bump_version

        bump_version("major", stage="rc")
        assert tag_calls[-1] == "v2.0.0rc1"

    def test_bump_with_short_stage_names(self, mock_clean_repo_no_tags, tag_calls):
        from common_python_tasks.tasks import bump_version

        # Test short stage names
        bump_version("patch", stage="a")
        assert tag_calls[-1] == "v0.0.1a1"

        tag_calls.clear()
        bump_version("patch", stage="b")
        assert tag_calls[-1] == "v0.0.1b1"

    def test_dry_run_no_tags(self, mock_clean_repo_no_tags, tag_calls):
        from common_python_tasks.tasks import bump_version

        with patch("common_python_tasks.tasks.LOGGER") as mock_logger:
            bump_version("patch", dry_run=True)
            mock_logger.info.assert_called_with(
                "Dry run: would bump version to %s", "0.0.1"
            )
            assert len(tag_calls) == 0  # No tag should be created in dry run

    def test_dry_run_with_existing_tag(self, mock_clean_repo_with_tag, tag_calls):
        from common_python_tasks.tasks import bump_version

        with patch("common_python_tasks.tasks.LOGGER") as mock_logger:
            bump_version("minor", stage="alpha", dry_run=True)
            mock_logger.info.assert_called_with(
                "Dry run: would bump version to %s", "1.3.0a1"
            )
            assert len(tag_calls) == 0  # No tag should be created in dry run

    def test_invalid_component_fails(self):
        from common_python_tasks.tasks import bump_version

        with patch("common_python_tasks.tasks._get_dirty_files") as mock_dirty:
            mock_dirty.return_value = []
            with patch("common_python_tasks.tasks.LOGGER"):
                with pytest.raises(SystemExit) as exc_info:
                    bump_version("invalid")
                assert exc_info.value.code == 1

    def test_invalid_stage_fails(self):
        from common_python_tasks.tasks import bump_version

        with patch("common_python_tasks.tasks._get_dirty_files") as mock_dirty:
            mock_dirty.return_value = []
            with patch("common_python_tasks.tasks.LOGGER"):
                with pytest.raises(SystemExit) as exc_info:
                    bump_version("patch", stage="invalid")
                assert exc_info.value.code == 1

    def test_dirty_repo_fails(self):
        from common_python_tasks.tasks import bump_version

        with patch("common_python_tasks.tasks._get_dirty_files") as mock_dirty:
            mock_dirty.return_value = ["modified_file.py"]
            with patch("common_python_tasks.tasks.LOGGER"):
                with pytest.raises(SystemExit) as exc_info:
                    bump_version("patch")
                assert exc_info.value.code == 1

    def test_case_insensitive_component(self, mock_clean_repo_no_tags, tag_calls):
        from common_python_tasks.tasks import bump_version

        bump_version("MAJOR")
        assert tag_calls[-1] == "v1.0.0"

        tag_calls.clear()
        bump_version("Minor")
        assert tag_calls[-1] == "v0.1.0"

    def test_case_insensitive_stage(self, mock_clean_repo_no_tags, tag_calls):
        from common_python_tasks.tasks import bump_version

        bump_version("patch", stage="ALPHA")
        assert tag_calls[-1] == "v0.0.1a1"

        tag_calls.clear()
        bump_version("patch", stage="Beta")
        assert tag_calls[-1] == "v0.0.1b1"

    def test_tag_without_v_prefix(self, tag_calls):
        """Test bumping from a tag that doesn't have 'v' prefix."""
        from common_python_tasks.tasks import bump_version

        with patch("common_python_tasks.tasks._get_dirty_files") as mock_dirty:
            with patch("common_python_tasks.tasks._run_command") as mock_run:
                mock_dirty.return_value = []  # Clean repo

                def side_effect(command, *args, **kwargs):
                    result = MagicMock()
                    if command[:4] == ["git", "describe", "--tags", "--abbrev=0"]:
                        result.returncode = 0
                        result.stdout = "1.2.3"  # No 'v' prefix
                    elif (
                        len(command) >= 3
                        and command[0] == "git"
                        and command[1] == "tag"
                    ):
                        result.returncode = 0
                        tag_calls.append(command[-1])
                        result.stdout = ""
                    else:
                        result.returncode = 0
                        result.stdout = ""
                    return result

                mock_run.side_effect = side_effect
                bump_version("patch")
                assert tag_calls[-1] == "v1.2.4"
