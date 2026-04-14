import json
import urllib.error
from importlib import metadata
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest
from common_python_tasks.utils import is_package_installed


@pytest.fixture
def mock_find_spec():
    """Mock importlib.util.find_spec for package availability testing."""
    with patch("importlib.util.find_spec") as mock:
        yield mock


def test_is_package_installed_when_installed(mock_find_spec):
    """Test _is_package_installed returns True when package is found."""
    from common_python_tasks.utils import is_package_installed

    mock_find_spec.return_value = MagicMock()

    is_package_installed.cache_clear()

    assert is_package_installed("black") is True
    mock_find_spec.assert_called_with("black")


def test_is_package_installed_when_not_installed(mock_find_spec):
    """Test _is_package_installed returns False when package is not found."""
    from common_python_tasks.utils import is_package_installed

    mock_find_spec.return_value = None

    is_package_installed.cache_clear()

    assert is_package_installed("black") is False
    mock_find_spec.assert_called_with("black")


def test_is_package_installed_handles_dashes(mock_find_spec):
    """Test _is_package_installed converts dashes to underscores."""
    from common_python_tasks.utils import is_package_installed

    mock_find_spec.return_value = MagicMock()

    is_package_installed.cache_clear()

    assert is_package_installed("pytest-cov") is True
    mock_find_spec.assert_called_with("pytest_cov")


def test_is_package_installed_caches_results(mock_find_spec):
    """Test _is_package_installed caches results."""
    from common_python_tasks.utils import is_package_installed

    mock_find_spec.return_value = MagicMock()

    is_package_installed.cache_clear()

    is_package_installed("black")
    is_package_installed("black")

    assert mock_find_spec.call_count == 1


def test_inject_auto_build_args_from_env_adds_value(monkeypatch):
    from common_python_tasks.utils import inject_auto_build_args_from_env

    monkeypatch.setenv("WORKDIR_PATH", "/app")

    result = inject_auto_build_args_from_env({})

    assert result["WORKDIR_PATH"] == "/app"


def test_inject_auto_build_args_from_env_preserves_explicit_value(monkeypatch):
    from common_python_tasks.utils import inject_auto_build_args_from_env

    monkeypatch.setenv("WORKDIR_PATH", "/app")

    result = inject_auto_build_args_from_env({"WORKDIR_PATH": "/custom"})

    assert result["WORKDIR_PATH"] == "/custom"


def test_get_compose_env_includes_workdir_path_default(monkeypatch):
    from common_python_tasks.utils import get_compose_env

    monkeypatch.delenv("WORKDIR_PATH", raising=False)

    env = get_compose_env()

    assert env["WORKDIR_PATH"] == "/workspace"


def test_get_compose_env_uses_workdir_path_from_env(monkeypatch):
    from common_python_tasks.utils import get_compose_env

    monkeypatch.setenv("WORKDIR_PATH", "/app")

    env = get_compose_env()

    assert env["WORKDIR_PATH"] == "/app"


def test_get_required_vars_for_files_includes_workdir_path_for_compose_db():
    from common_python_tasks.utils import get_required_vars_for_files

    vars_required = get_required_vars_for_files("fastapi", [Path("compose-db.yml")])

    assert "WORKDIR_PATH" in vars_required


def test_get_installed_requirement_version_strips_extras_and_normalizes_name():
    """Test _get_installed_requirement_version returns the installed version."""
    from common_python_tasks.utils import get_installed_requirement_version

    def version_side_effect(name):
        if name == "poetry-dynamic-versioning":
            return "0.17.0"
        raise metadata.PackageNotFoundError

    get_installed_requirement_version.cache_clear()
    with patch("importlib.metadata.version", side_effect=version_side_effect):
        assert (
            get_installed_requirement_version("poetry-dynamic-versioning[plugin]")
            == "0.17.0"
        )


def test_get_installed_requirement_version_uses_poetry_show_when_not_available_in_metadata():
    """Test _get_installed_requirement_version falls back to poetry show."""
    from common_python_tasks.utils import get_installed_requirement_version

    def version_side_effect(name):
        raise metadata.PackageNotFoundError

    poetry_show_output = """
 name         : poetry-dynamic-versioning
 version      : 1.8.2
 description  : Plugin for Poetry to enable dynamic versioning based on VCS tags
"""

    get_installed_requirement_version.cache_clear()

    def run_command_side_effect(
        cmd, capture_output=True, acceptable_returncodes=None, env=None
    ):
        if cmd[:3] == ["poetry", "run", "python"]:
            return MagicMock(stdout="", returncode=1)
        if cmd == ["poetry", "show", "poetry-dynamic-versioning"]:
            return MagicMock(stdout=poetry_show_output, returncode=0)
        return MagicMock(stdout="", returncode=1)

    with (
        patch("importlib.metadata.version", side_effect=version_side_effect),
        patch(
            "common_python_tasks.utils.get_local_poetry_plugin_version",
            return_value=None,
        ),
        patch(
            "common_python_tasks.utils.run_command",
            side_effect=run_command_side_effect,
        ),
    ):
        assert (
            get_installed_requirement_version("poetry-dynamic-versioning[plugin]")
            == "1.8.2"
        )


def test_get_installed_requirement_version_uses_poetry_self_show_when_poetry_show_fails():
    """Test _get_installed_requirement_version falls back to poetry self show."""
    from common_python_tasks.utils import get_installed_requirement_version

    def version_side_effect(name):
        raise metadata.PackageNotFoundError

    poetry_self_show_output = """
 name         : poetry-dynamic-versioning
 version      : 1.8.3
 description  : Plugin for Poetry to enable dynamic versioning based on VCS tags
"""

    get_installed_requirement_version.cache_clear()

    def run_command_side_effect(
        cmd, capture_output=True, acceptable_returncodes=None, env=None
    ):
        if cmd[:3] == ["poetry", "run", "python"]:
            return MagicMock(stdout="", returncode=1)
        if cmd == ["poetry", "show", "poetry-dynamic-versioning"]:
            return MagicMock(stdout="", returncode=1)
        if cmd == ["poetry", "self", "show", "poetry-dynamic-versioning"]:
            return MagicMock(stdout=poetry_self_show_output, returncode=0)
        return MagicMock(stdout="", returncode=1)

    with (
        patch("importlib.metadata.version", side_effect=version_side_effect),
        patch(
            "common_python_tasks.utils.get_local_poetry_plugin_version",
            return_value=None,
        ),
        patch(
            "common_python_tasks.utils.run_command",
            side_effect=run_command_side_effect,
        ),
    ):
        assert (
            get_installed_requirement_version("poetry-dynamic-versioning[plugin]")
            == "1.8.3"
        )


def test_run_command_executes_shell_command():
    from common_python_tasks.utils import run_command

    with patch("common_python_tasks.utils.subprocess.run") as mock_subprocess:
        mock_subprocess.return_value = MagicMock(returncode=0, stdout="")
        run_command(["sh", "-lc", "echo hello"], env={"RELEASE_VERSION": "1.2.3"})

        mock_subprocess.assert_called_once()


def test_run_command_logs_dry_run():
    from common_python_tasks.utils import run_command

    with patch("common_python_tasks.utils.log_dry_run") as mock_log:
        result = run_command(["sh", "-lc", "echo hello"], dry_run=True)

        assert result is None
        mock_log.assert_called_once_with("Would run command: %s", "sh -lc echo hello")


def test_build_with_containers_calls_task_build_image():
    from common_python_tasks.utils import build

    with (
        patch("common_python_tasks.tasks.build_package") as mock_build_package,
        patch("common_python_tasks.tasks.build_image") as mock_build_image,
    ):
        build(
            has_containers=True, debug=True, no_cache=True, plain=True, single_arch=True
        )

    mock_build_package.assert_called_once_with()
    mock_build_image.assert_called_once_with(
        debug=True,
        no_cache=True,
        plain=True,
        single_arch=True,
        build_args=None,
        container_env=None,
        container_envfile=None,
    )


def test_build_forwards_container_build_options():
    from common_python_tasks.utils import build

    with (
        patch("common_python_tasks.tasks.build_package") as mock_build_package,
        patch("common_python_tasks.tasks.build_image") as mock_build_image,
    ):
        build(
            has_containers=True,
            debug=True,
            no_cache=True,
            plain=True,
            single_arch=True,
            build_args="FOO=bar",
            container_env="X=1",
            container_envfile="env1.env:env2.env",
        )

    mock_build_package.assert_called_once_with()
    mock_build_image.assert_called_once_with(
        debug=True,
        no_cache=True,
        plain=True,
        single_arch=True,
        build_args="FOO=bar",
        container_env="X=1",
        container_envfile="env1.env:env2.env",
    )


def test_build_without_containers_skips_task_build_image():
    from common_python_tasks.utils import build

    with (
        patch("common_python_tasks.tasks.build_package") as mock_build_package,
        patch("common_python_tasks.tasks.build_image") as mock_build_image,
    ):
        build(has_containers=False)

    mock_build_package.assert_called_once_with()
    mock_build_image.assert_not_called()


def test_get_installed_requirement_version_uses_poetry_run_python_when_metadata_fails():
    """Test _get_installed_requirement_version falls back to Poetry's runtime environment."""
    from common_python_tasks.utils import get_installed_requirement_version

    def version_side_effect(name):
        raise metadata.PackageNotFoundError

    get_installed_requirement_version.cache_clear()
    with (
        patch("importlib.metadata.version", side_effect=version_side_effect),
        patch(
            "common_python_tasks.utils.get_local_poetry_plugin_version",
            return_value=None,
        ),
        patch(
            "common_python_tasks.utils.run_command",
            return_value=MagicMock(stdout="1.9.0\n", returncode=0),
        ),
    ):
        assert get_installed_requirement_version("poetry-plugin-export") == "1.9.0"


def test_get_installed_requirement_version_uses_local_poetry_plugins_directory(
    tmp_path, monkeypatch
):
    """Test _get_installed_requirement_version reads .poetry/plugins METADATA."""
    from common_python_tasks.utils import get_installed_requirement_version

    monkeypatch.chdir(tmp_path)
    metadata_dir = (
        tmp_path / ".poetry" / "plugins" / "poetry_plugin_export-1.10.0.dist-info"
    )
    metadata_dir.mkdir(parents=True)
    metadata_dir.joinpath("METADATA").write_text(
        "Name: poetry-plugin-export\nVersion: 1.10.0\n", encoding="utf-8"
    )

    def version_side_effect(name):
        raise metadata.PackageNotFoundError

    get_installed_requirement_version.cache_clear()
    with patch("importlib.metadata.version", side_effect=version_side_effect):
        assert get_installed_requirement_version("poetry-plugin-export") == "1.10.0"


def test_get_installed_requirement_version_returns_none_when_not_installed():
    """Test _get_installed_requirement_version returns None when missing."""
    from common_python_tasks.utils import get_installed_requirement_version

    def version_side_effect(name):
        raise metadata.PackageNotFoundError

    get_installed_requirement_version.cache_clear()
    with patch("importlib.metadata.version", side_effect=version_side_effect):
        assert get_installed_requirement_version("no-such-package") is None


def test_fatal_logs_and_exits():
    """Test _fatal logs error and exits with correct code."""
    from common_python_tasks.utils import fatal

    with patch("common_python_tasks.utils.LOGGER") as mock_logger:
        with pytest.raises(SystemExit) as exc_info:
            fatal("Test error message")

        mock_logger.critical.assert_called_once_with("Test error message")
        assert exc_info.value.code == 1


def test_fatal_with_custom_exit_code():
    """Test _fatal uses custom exit code."""
    from common_python_tasks.utils import fatal

    with patch("common_python_tasks.utils.LOGGER"):
        with pytest.raises(SystemExit) as exc_info:
            fatal("Test error", exit_code=42)

        assert exc_info.value.code == 42


def test_require_package_succeeds_when_installed(mock_find_spec):
    """Test _require_package succeeds when package is installed."""
    from common_python_tasks.utils import require_package

    mock_find_spec.return_value = MagicMock()
    is_package_installed.cache_clear()

    require_package("black")


def test_require_package_fails_when_not_installed(mock_find_spec):
    """Test _require_package exits when package is not installed."""
    from common_python_tasks.utils import require_package

    mock_find_spec.return_value = None
    is_package_installed.cache_clear()

    with patch("common_python_tasks.utils.LOGGER"):
        with pytest.raises(SystemExit) as exc_info:
            require_package("black")

        assert exc_info.value.code == 1


def test_run_available_tools_runs_installed_tools(mock_find_spec):
    """Test _run_available_tools runs only installed tools."""
    from common_python_tasks.utils import run_available_tools

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
    """Test _run_available_tools exits when no tools are installed."""
    from common_python_tasks.utils import run_available_tools

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
    """Test _run_available_tools runs all tools when all are installed."""
    from common_python_tasks.utils import run_available_tools

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


def test_infer_bump_component_from_git_cliff_returns_expected_bump():
    """Test auto bump inference from git-cliff output."""
    from common_python_tasks.utils import infer_bump_component_from_git_cliff

    with (
        patch("shutil.which", return_value="/usr/bin/git-cliff"),
        patch(
            "common_python_tasks.utils.run_command",
            return_value=MagicMock(stdout="v2.0.0\n", returncode=0),
        ),
        patch(
            "common_python_tasks.utils.get_project_version_from_poetry",
            return_value="1.3.2",
        ),
    ):
        assert infer_bump_component_from_git_cliff() == "major"


def test_format_all_uses_run_available_tools(mock_find_spec):
    """Test format_all task uses _run_available_tools correctly."""
    from common_python_tasks.tasks import format_all

    is_package_installed.cache_clear()
    mock_find_spec.return_value = MagicMock()

    with patch("common_python_tasks.utils.run_command") as mock_cmd:
        format_all()

        assert mock_cmd.call_count == 3


def test_lint_all_uses_run_available_tools(mock_find_spec):
    """Test lint_all task uses _run_available_tools correctly."""
    from common_python_tasks.tasks import lint_all

    is_package_installed.cache_clear()
    mock_find_spec.return_value = MagicMock()

    with patch("common_python_tasks.utils.run_command") as mock_cmd:
        with patch("common_python_tasks.utils.get_config_path") as mock_config:
            mock_config.return_value = ".flake8"
            lint_all()

        assert mock_cmd.call_count == 4


def test_format_all_fails_when_no_tools_installed(mock_find_spec):
    """Test format_all exits when no formatting tools are installed."""
    from common_python_tasks.tasks import format_all

    is_package_installed.cache_clear()
    mock_find_spec.return_value = None

    with patch("common_python_tasks.utils.LOGGER"):
        with pytest.raises(SystemExit) as exc_info:
            format_all()

        assert exc_info.value.code == 1


def test_lint_all_fails_when_no_tools_installed(mock_find_spec):
    """Test lint_all exits when no linting tools are installed."""
    from common_python_tasks.tasks import lint_all

    is_package_installed.cache_clear()
    mock_find_spec.return_value = None

    with patch("common_python_tasks.utils.LOGGER"):
        with pytest.raises(SystemExit) as exc_info:
            lint_all()

        assert exc_info.value.code == 1


class TestHasTagsLaterInHistory:
    """Tests for checking if there are tags later in git history."""

    def test_no_tags_exist(self):
        """Test when no tags exist in the repository."""
        from common_python_tasks.utils import has_tags_later_in_history

        with patch("common_python_tasks.utils.run_command") as mock:

            def side_effect(command, *args, **kwargs):
                result = MagicMock()
                if command == ["git", "tag"]:
                    result.returncode = 0
                    result.stdout = ""
                return result

            mock.side_effect = side_effect

            assert not has_tags_later_in_history()

    def test_no_tags_later_in_history(self):
        """Test when all tags are ancestors of current HEAD."""
        from common_python_tasks.utils import has_tags_later_in_history

        with patch("common_python_tasks.utils.run_command") as mock:

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

            assert not has_tags_later_in_history()

    def test_has_tags_later_in_history(self):
        """Test when there are tags not reachable from current HEAD."""
        from common_python_tasks.utils import has_tags_later_in_history

        with patch("common_python_tasks.utils.run_command") as mock:
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

            assert has_tags_later_in_history()

    def test_git_tag_command_fails(self):
        """Test when git tag command fails."""
        from common_python_tasks.utils import has_tags_later_in_history

        with patch("common_python_tasks.utils.run_command") as mock:

            def side_effect(command, *args, **kwargs):
                result = MagicMock()
                if command == ["git", "tag"]:
                    result.returncode = 128
                    result.stdout = ""
                return result

            mock.side_effect = side_effect

            assert not has_tags_later_in_history()


class TestBumpVersion:
    """Tests for version bumping functionality."""

    @pytest.fixture
    def tag_calls(self):
        """Collect git tag arguments issued by bump_version."""
        return []

    @pytest.fixture
    def mock_clean_repo_no_tags(self, tag_calls):
        """Mock clean repository with no existing tags."""
        with patch("common_python_tasks.utils.get_dirty_files") as mock_dirty:
            with patch(
                "common_python_tasks.utils.ensure_on_default_branch"
            ) as mock_default_branch:  # noqa: F841
                with patch(
                    "common_python_tasks.utils.get_project_version_from_poetry",
                    return_value="0.0.0",
                ):
                    with patch("common_python_tasks.utils.run_command") as mock_run:
                        mock_dirty.return_value = []  # Clean repo

                        def side_effect(command, *args, **kwargs):
                            result = MagicMock()
                            if (
                                len(command) >= 2
                                and str(command[0]) == "git"
                                and str(command[1]) == "tag"
                            ):
                                result.returncode = 0
                                tag_calls.append(str(command[-1]))
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
        with patch("common_python_tasks.utils.get_dirty_files") as mock_dirty:
            with patch(
                "common_python_tasks.utils.ensure_on_default_branch"
            ) as mock_default_branch:  # noqa: F841
                with patch(
                    "common_python_tasks.utils.get_project_version_from_poetry",
                    return_value="1.2.3",
                ):
                    with patch("common_python_tasks.utils.run_command") as mock_run:
                        mock_dirty.return_value = []  # Clean repo

                        def side_effect(command, *args, **kwargs):
                            result = MagicMock()
                            if (
                                len(command) >= 2
                                and str(command[0]) == "git"
                                and str(command[1]) == "tag"
                            ):
                                result.returncode = 0
                                tag_calls.append(str(command[-1]))
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

    def test_bump_version_defaults_to_auto(self, mock_clean_repo_with_tag, tag_calls):
        from common_python_tasks.tasks import bump_version

        def run_command_side_effect(command, *args, **kwargs):
            result = MagicMock()
            if (
                len(command) >= 2
                and str(command[0]) == "git"
                and str(command[1]) == "tag"
            ):
                result.returncode = 0
                tag_calls.append(str(command[-1]))
                result.stdout = ""
            else:
                result.returncode = 0
                result.stdout = ""
            return result

        with (
            patch(
                "common_python_tasks.utils.infer_bump_component_from_git_cliff",
                return_value="minor",
            ),
            patch(
                "common_python_tasks.utils.run_command",
                side_effect=run_command_side_effect,
            ),
        ):
            bump_version()

        assert tag_calls[-1] == "v1.3.0"

    def test_bump_version_auto_for_pre_production_forces_patch(self, tag_calls):
        from common_python_tasks.tasks import bump_version

        def run_command_side_effect(command, *args, **kwargs):
            result = MagicMock()
            if (
                len(command) >= 2
                and str(command[0]) == "git"
                and str(command[1]) == "tag"
            ):
                result.returncode = 0
                tag_calls.append(str(command[-1]))
                result.stdout = ""
            else:
                result.returncode = 0
                result.stdout = ""
            return result

        with (
            patch("common_python_tasks.utils.ensure_on_default_branch"),
            patch(
                "common_python_tasks.utils.infer_bump_component_from_git_cliff",
                return_value="major",
            ),
            patch(
                "common_python_tasks.utils.get_project_version_from_poetry",
                return_value="0.2.5",
            ),
            patch(
                "common_python_tasks.utils.get_dirty_files",
                return_value=[],
            ),
            patch(
                "common_python_tasks.utils.run_command",
                side_effect=run_command_side_effect,
            ),
        ):
            bump_version()

        assert tag_calls[-1] == "v0.2.6"

    def test_bump_version_requires_default_branch(self, tag_calls):
        from common_python_tasks.tasks import bump_version

        with (
            patch(
                "common_python_tasks.utils.ensure_on_default_branch",
                side_effect=SystemExit(1),
            ),
            patch(
                "common_python_tasks.utils.get_project_version_from_poetry",
                return_value="0.2.5",
            ),
            patch(
                "common_python_tasks.utils.get_dirty_files",
                return_value=[],
            ),
            patch(
                "common_python_tasks.utils.run_command",
                return_value=MagicMock(returncode=0, stdout=""),
            ),
        ):
            with pytest.raises(SystemExit):
                bump_version()

        assert tag_calls == []

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

        bump_version("patch", stage="a")
        assert tag_calls[-1] == "v0.0.1a1"

        tag_calls.clear()
        bump_version("patch", stage="b")
        assert tag_calls[-1] == "v0.0.1b1"

    def test_dry_run_no_tags(self, mock_clean_repo_no_tags, tag_calls):
        from common_python_tasks.tasks import bump_version

        with patch("common_python_tasks.utils.LOGGER") as mock_logger:
            bump_version("patch", dry_run=True)
            mock_logger.info.assert_called_with(
                "\033[93m[DRY RUN]\033[0m Would bump version to %s",
                "0.0.1",
            )
            assert len(tag_calls) == 0  # No tag should be created in dry run

    def test_dry_run_with_existing_tag(self, mock_clean_repo_with_tag, tag_calls):
        from common_python_tasks.tasks import bump_version

        with patch("common_python_tasks.utils.LOGGER") as mock_logger:
            bump_version("minor", stage="alpha", dry_run=True)
            mock_logger.info.assert_called_with(
                "\033[93m[DRY RUN]\033[0m Would bump version to %s",
                "1.3.0a1",
            )
            assert len(tag_calls) == 0  # No tag should be created in dry run

    def test_invalid_component_fails(self):
        from common_python_tasks.tasks import bump_version

        with (
            patch("common_python_tasks.utils.ensure_on_default_branch"),
            patch("common_python_tasks.utils.get_dirty_files") as mock_dirty,
        ):
            mock_dirty.return_value = []
            with patch("common_python_tasks.utils.LOGGER"):
                with pytest.raises(SystemExit) as exc_info:
                    bump_version("invalid")
                assert exc_info.value.code == 1

    def test_invalid_stage_fails(self):
        from common_python_tasks.tasks import bump_version

        with (
            patch("common_python_tasks.utils.ensure_on_default_branch"),
            patch("common_python_tasks.utils.get_dirty_files") as mock_dirty,
        ):
            mock_dirty.return_value = []
            with patch("common_python_tasks.utils.LOGGER"):
                with pytest.raises(SystemExit) as exc_info:
                    bump_version("patch", stage="invalid")
                assert exc_info.value.code == 1

    def test_dirty_repo_fails(self):
        from common_python_tasks.tasks import bump_version

        with (
            patch("common_python_tasks.utils.ensure_on_default_branch"),
            patch("common_python_tasks.utils.get_dirty_files") as mock_dirty,
        ):
            mock_dirty.return_value = ["modified_file.py"]
            with patch("common_python_tasks.utils.LOGGER"):
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

    def test_bump_from_dev_version(self, tag_calls):
        """Test bumping from a development version with PEP 440 suffixes."""
        from common_python_tasks.tasks import bump_version

        with (
            patch("common_python_tasks.utils.ensure_on_default_branch"),
            patch("common_python_tasks.utils.get_dirty_files") as mock_dirty,
        ):
            with patch(
                "common_python_tasks.utils.get_project_version_from_poetry",
                return_value="1.2.3.post2.dev0",
            ):
                with patch("common_python_tasks.utils.run_command") as mock_run:
                    mock_dirty.return_value = []

                    def side_effect(command, *args, **kwargs):
                        result = MagicMock()
                        if (
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


class TestTaskTagInclusion:
    """Tests for TOML-based Poe tag inclusion checks."""

    def test_is_task_tag_included_with_include_tags(self):
        from common_python_tasks.utils import is_task_tag_included

        is_task_tag_included.cache_clear()
        with patch("common_python_tasks.utils.read_pyproject_toml") as mock_toml:
            mock_toml.return_value = {
                "tool": {
                    "poe": {
                        "include_script": "common_python_tasks:tasks(include_tags=['format', 'containers'])"
                    }
                }
            }

            assert is_task_tag_included("containers") is True

    def test_is_task_tag_included_with_exclude_tags(self):
        from common_python_tasks.utils import is_task_tag_included

        is_task_tag_included.cache_clear()
        with patch("common_python_tasks.utils.read_pyproject_toml") as mock_toml:
            mock_toml.return_value = {
                "tool": {
                    "poe": {
                        "include_script": "common_python_tasks:tasks(exclude_tags=['containers', 'fastapi'])"
                    }
                }
            }

            assert is_task_tag_included("containers") is False

    def test_is_task_tag_included_defaults_true_without_filters(self):
        from common_python_tasks.utils import is_task_tag_included

        is_task_tag_included.cache_clear()
        with patch("common_python_tasks.utils.read_pyproject_toml") as mock_toml:
            mock_toml.return_value = {
                "tool": {"poe": {"include_script": "common_python_tasks:tasks()"}}
            }

            assert is_task_tag_included("containers") is True


class TestReleaseTask:
    """Tests for the release orchestration task."""

    def test_release_runs_packaging_only_when_containers_excluded(self):
        from common_python_tasks.tasks import release

        with (
            patch(
                "common_python_tasks.utils.ensure_on_default_branch"
            ) as mock_default_branch,  # noqa: F841
            patch("common_python_tasks.tasks.clean") as mock_clean,
            patch("common_python_tasks.tasks.bump_version") as mock_bump,
            patch("common_python_tasks.utils.run_command") as mock_run_command,
            patch("common_python_tasks.tasks.build_package") as mock_build_package,
            patch("common_python_tasks.tasks.publish_package") as mock_publish,
            patch(
                "common_python_tasks.utils.is_task_tag_included", return_value=False
            ) as mock_has_tag,
            patch(
                "common_python_tasks.utils.get_project_version_from_poetry",
                return_value="1.2.2",
            ),
            patch("common_python_tasks.utils.build_image") as mock_build_image,
            patch("common_python_tasks.tasks.push_image") as mock_push_image,
            patch(
                "common_python_tasks.utils.get_release_tag_from_poetry_version",
                return_value="v1.2.3",
            ),
            patch(
                "common_python_tasks.utils.get_github_release_asset_paths",
                return_value=[],
            ) as mock_get_asset_paths,  # noqa: F841
            patch(
                "common_python_tasks.utils.publish_github_release"
            ) as mock_publish_github_release,
        ):
            release(component="minor", stage="beta")

            mock_clean.assert_called_once_with()
            mock_bump.assert_called_once_with(
                component="minor", stage="beta", dry_run=False
            )
            mock_run_command.assert_called_once_with(
                ["git", "push", "origin", "v1.2.3"]
            )
            mock_build_package.assert_called_once_with(clean_dist=True)
            mock_publish.assert_called_once_with(build_first=False)
            mock_has_tag.assert_called_once_with("containers")
            mock_build_image.assert_not_called()
            mock_push_image.assert_not_called()
            mock_publish_github_release.assert_called_once_with(
                "v1.2.3",
                prerelease=True,
                assets=[],
            )

    def test_release_runs_container_steps_when_containers_included(self):
        from common_python_tasks.tasks import release

        with (
            patch(
                "common_python_tasks.utils.ensure_on_default_branch"
            ) as mock_default_branch,  # noqa: F841
            patch("common_python_tasks.tasks.clean") as mock_clean,
            patch("common_python_tasks.tasks.bump_version") as mock_bump,
            patch("common_python_tasks.utils.run_command") as mock_run_command,
            patch("common_python_tasks.tasks.build_package") as mock_build_package,
            patch("common_python_tasks.tasks.publish_package") as mock_publish,
            patch(
                "common_python_tasks.utils.is_task_tag_included", return_value=True
            ) as mock_has_tag,
            patch(
                "common_python_tasks.utils.get_project_version_from_poetry",
                return_value="1.2.2",
            ),
            patch("common_python_tasks.utils.build_image") as mock_build_image,
            patch("common_python_tasks.tasks.push_image") as mock_push_image,
            patch(
                "common_python_tasks.utils.get_release_tag_from_poetry_version",
                return_value="v1.2.3",
            ),
            patch(
                "common_python_tasks.utils.get_github_release_asset_paths",
                return_value=[],
            ) as mock_get_asset_paths,  # noqa: F841
            patch(
                "common_python_tasks.utils.publish_github_release"
            ) as mock_publish_github_release,
        ):
            release(debug=True, no_cache=True, plain=True, single_arch=True)

            mock_clean.assert_called_once_with()
            mock_bump.assert_called_once_with(
                component="patch", stage=None, dry_run=False
            )
            mock_run_command.assert_called_once_with(
                ["git", "push", "origin", "v1.2.3"]
            )
            mock_build_package.assert_called_once_with(clean_dist=True)
            mock_publish.assert_called_once_with(build_first=False)
            mock_has_tag.assert_called_once_with("containers")
            mock_build_image.assert_called_once_with(
                debug=True,
                no_cache=True,
                plain=True,
                single_arch=True,
                build_args=None,
                container_env=None,
                container_envfile=None,
            )
            mock_push_image.assert_called_once_with(debug=True)
            mock_publish_github_release.assert_called_once_with(
                "v1.2.3",
                prerelease=False,
                assets=[],
            )

    def test_release_runs_pre_and_post_scripts(self):
        from common_python_tasks.tasks import release

        with (
            patch("common_python_tasks.utils.ensure_on_default_branch"),
            patch("common_python_tasks.tasks.clean") as mock_clean,
            patch("common_python_tasks.tasks.bump_version") as mock_bump,
            patch(
                "common_python_tasks.tasks.build_package"
            ) as mock_build_package,  # noqa: F841
            patch(
                "common_python_tasks.tasks.publish_package"
            ) as mock_publish,  # noqa: F841
            patch("common_python_tasks.utils.run_command") as mock_run_command,
            patch(
                "common_python_tasks.utils.is_task_tag_included",
                return_value=False,
            ) as mock_has_tag,  # noqa: F841
            patch(
                "common_python_tasks.utils.get_project_version_from_poetry",
                return_value="0.0.1",
            ),
            patch(
                "common_python_tasks.utils.get_release_tag_from_poetry_version",
                return_value="v0.0.2",
            ),
            patch(
                "common_python_tasks.utils.get_github_release_asset_paths",
                return_value=[],
            ) as mock_get_asset_paths,  # noqa: F841
            patch(
                "common_python_tasks.utils.publish_github_release"
            ) as mock_publish_github_release,  # noqa: F841
        ):
            release(
                component="patch",
                pre_script="echo pre",
                post_script="echo post",
            )

            mock_clean.assert_called_once_with()
            mock_bump.assert_called_once_with(
                component="patch", stage=None, dry_run=False
            )
            mock_run_command.assert_any_call(
                [
                    "git",
                    "push",
                    "origin",
                    "v0.0.2",
                ]
            )
            mock_run_command.assert_any_call(
                ["sh", "-lc", "echo pre"],
                env=ANY,
                dry_run=False,
            )
            mock_run_command.assert_any_call(
                ["sh", "-lc", "echo post"],
                env=ANY,
                dry_run=False,
            )

            first_hook_env = mock_run_command.call_args_list[0].kwargs["env"]
            assert first_hook_env["RELEASE_TAG"] == "v0.0.2"
            assert first_hook_env["RELEASE_VERSION"] == "0.0.2"
            assert first_hook_env["RELEASE_COMPONENT"] == "patch"
            assert first_hook_env["RELEASE_DRY_RUN"] == "0"

    def test_release_dry_run_only_bumps_version(self):
        from common_python_tasks.tasks import release

        with (
            patch(
                "common_python_tasks.utils.ensure_on_default_branch"
            ) as mock_default_branch,  # noqa: F841
            patch("common_python_tasks.tasks.clean") as mock_clean,
            patch("common_python_tasks.tasks.bump_version") as mock_bump,
            patch("common_python_tasks.tasks.build_package") as mock_build_package,
            patch("common_python_tasks.tasks.publish_package") as mock_publish,
            patch(
                "common_python_tasks.utils.is_task_tag_included", return_value=True
            ) as mock_has_tag,
            patch(
                "common_python_tasks.utils.get_project_version_from_poetry",
                return_value="1.2.2",
            ),
            patch("common_python_tasks.utils.build_image") as mock_build_image,
            patch("common_python_tasks.tasks.push_image") as mock_push_image,
            patch("common_python_tasks.utils.LOGGER") as mock_logger,
            patch(
                "common_python_tasks.utils.publish_github_release"
            ) as mock_publish_github_release,
            patch(
                "common_python_tasks.utils.run_command"
            ) as mock_run_command,  # noqa: F841
        ):
            release(component="patch", dry_run=True)

            mock_clean.assert_not_called()
            mock_bump.assert_called_once_with(
                component="patch", stage=None, dry_run=True
            )
            mock_build_package.assert_not_called()
            mock_publish.assert_not_called()
            mock_has_tag.assert_called_once_with("containers")
            mock_build_image.assert_not_called()
            mock_push_image.assert_not_called()
            mock_publish_github_release.assert_not_called()
            mock_logger.info.assert_any_call(
                "\033[93m[DRY RUN]\033[0m Would clean generated artifacts before release"
            )
            mock_logger.info.assert_any_call(
                "\033[93m[DRY RUN]\033[0m Would push tags to origin"
            )
            mock_logger.info.assert_any_call(
                "\033[93m[DRY RUN]\033[0m Would build package with clean_dist=True"
            )
            mock_logger.info.assert_any_call(
                "\033[93m[DRY RUN]\033[0m Would publish package with build_first=False"
            )
            mock_logger.info.assert_any_call(
                "\033[93m[DRY RUN]\033[0m Would build container image with debug=%s no_cache=%s plain=%s single_arch=%s",
                False,
                False,
                False,
                False,
            )
            mock_logger.info.assert_any_call(
                "\033[93m[DRY RUN]\033[0m Would push container image with debug=%s",
                False,
            )

    def test_release_accepts_none_stage_string(self):
        from common_python_tasks.tasks import release

        with (
            patch(
                "common_python_tasks.utils.ensure_on_default_branch"
            ) as mock_default_branch,  # noqa: F841
            patch("common_python_tasks.tasks.clean") as mock_clean,
            patch("common_python_tasks.tasks.bump_version") as mock_bump,
            patch("common_python_tasks.utils.run_command") as mock_run_command,
            patch("common_python_tasks.tasks.build_package") as mock_build_package,
            patch("common_python_tasks.tasks.publish_package") as mock_publish,
            patch(
                "common_python_tasks.utils.is_task_tag_included", return_value=False
            ) as mock_has_tag,
            patch(
                "common_python_tasks.utils.get_project_version_from_poetry",
                return_value="1.2.2",
            ),
            patch(
                "common_python_tasks.utils.get_release_tag_from_poetry_version",
                return_value="v1.2.3",
            ),
            patch(
                "common_python_tasks.utils.get_github_release_asset_paths",
                return_value=[],
            ) as mock_get_asset_paths,  # noqa: F841
            patch(
                "common_python_tasks.utils.publish_github_release"
            ) as mock_publish_github_release,
        ):
            release(component="patch", stage="none")

            mock_clean.assert_called_once_with()
            mock_bump.assert_called_once_with(
                component="patch", stage=None, dry_run=False
            )
            mock_run_command.assert_called_once_with(
                ["git", "push", "origin", "v1.2.3"]
            )
            mock_build_package.assert_called_once_with(clean_dist=True)
            mock_publish.assert_called_once_with(build_first=False)
            mock_has_tag.assert_called_once_with("containers")
            mock_publish_github_release.assert_called_once_with(
                "v1.2.3",
                prerelease=False,
                assets=[],
            )

    def test_release_fails_when_not_on_default_branch(self):
        from common_python_tasks.tasks import release

        def run_command_side_effect(
            cmd, capture_output=False, acceptable_returncodes=None, env=None
        ):
            if cmd == ["git", "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"]:
                return MagicMock(returncode=0, stdout="refs/remotes/origin/main\n")
            if cmd == ["git", "branch", "--show-current"]:
                return MagicMock(returncode=0, stdout="feature/branch\n")
            return MagicMock(returncode=0, stdout="")

        with patch(
            "common_python_tasks.utils.run_command",
            side_effect=run_command_side_effect,
        ):
            with pytest.raises(SystemExit) as exc_info:
                release()

        assert exc_info.value.code == 1


class TestGitHubReleasePublishing:
    """Tests for the GitHub Release publishing helper."""

    def test_publish_github_release_creates_release_when_missing(self):
        from common_python_tasks.tasks import publish_github_release

        requests = []

        class FakeResponse:
            def __init__(self, payload: dict[str, object]):
                self._payload = json.dumps(payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return self._payload

        def urlopen_side_effect(request):
            requests.append(
                {
                    "method": request.get_method(),
                    "url": request.full_url,
                    "data": request.data,
                }
            )
            if request.get_method() == "GET":
                raise urllib.error.HTTPError(
                    request.full_url, 404, "Not Found", None, None
                )
            return FakeResponse({"id": 123, "tag_name": "v1.2.3"})

        with (
            patch(
                "common_python_tasks.utils.should_publish_github_release",
                return_value=True,
            ),
            patch(
                "common_python_tasks.utils.get_github_repository",
                return_value="ci-sourcerer/common-python-tasks",
            ),
            patch("common_python_tasks.utils.get_github_token", return_value="token"),
            patch(
                "common_python_tasks.utils.get_github_release_asset_paths",
                return_value=[],
            ),
            patch(
                "common_python_tasks.utils.urllib.request.urlopen",
                side_effect=urlopen_side_effect,
            ),
        ):
            result = publish_github_release(
                "v1.2.3",
                release_name="v1.2.3",
                body="Release v1.2.3",
            )

        assert result == {"id": 123, "tag_name": "v1.2.3"}
        assert [request["method"] for request in requests] == ["GET", "POST"]
        assert json.loads(requests[1]["data"].decode("utf-8")) == {
            "tag_name": "v1.2.3",
            "name": "v1.2.3",
            "body": "Release v1.2.3",
            "draft": False,
            "prerelease": False,
        }

    def test_publish_github_release_uses_git_cliff_for_release_notes_if_no_body_is_provided(
        self,
    ):
        from common_python_tasks.tasks import publish_github_release

        requests = []
        changelog = "## Unreleased\n- Fix critical bug\n"

        class FakeResponse:
            def __init__(self, payload: dict[str, object]):
                self._payload = json.dumps(payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return self._payload

        def urlopen_side_effect(request):
            requests.append(
                {
                    "method": request.get_method(),
                    "url": request.full_url,
                    "data": request.data,
                }
            )
            if request.get_method() == "GET":
                raise urllib.error.HTTPError(
                    request.full_url, 404, "Not Found", None, None
                )
            return FakeResponse({"id": 123, "tag_name": "v1.2.3"})

        with (
            patch(
                "common_python_tasks.utils.should_publish_github_release",
                return_value=True,
            ),
            patch(
                "common_python_tasks.utils.get_github_repository",
                return_value="ci-sourcerer/common-python-tasks",
            ),
            patch("common_python_tasks.utils.get_github_token", return_value="token"),
            patch("shutil.which", return_value="/usr/bin/git-cliff"),
            patch(
                "common_python_tasks.utils.run_command",
                return_value=MagicMock(stdout=changelog, returncode=0),
            ),
            patch(
                "common_python_tasks.utils.get_github_release_asset_paths",
                return_value=[],
            ),
            patch(
                "common_python_tasks.utils.urllib.request.urlopen",
                side_effect=urlopen_side_effect,
            ),
        ):
            result = publish_github_release(
                "v1.2.3",
                release_name="v1.2.3",
            )

        assert result == {"id": 123, "tag_name": "v1.2.3"}
        assert [request["method"] for request in requests] == ["GET", "POST"]
        assert json.loads(requests[1]["data"].decode("utf-8")) == {
            "tag_name": "v1.2.3",
            "name": "v1.2.3",
            "body": changelog.strip(),
            "draft": False,
            "prerelease": False,
        }

    def test_publish_github_release_updates_existing_release(self):
        from common_python_tasks.tasks import publish_github_release

        requests = []

        class FakeResponse:
            def __init__(self, payload: dict[str, object]):
                self._payload = json.dumps(payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return self._payload

        def urlopen_side_effect(request):
            requests.append(
                {
                    "method": request.get_method(),
                    "url": request.full_url,
                    "data": request.data,
                }
            )
            if request.get_method() == "GET":
                return FakeResponse({"id": 321, "tag_name": "v1.2.3"})
            return FakeResponse({"id": 321, "tag_name": "v1.2.3", "body": "Updated"})

        with (
            patch(
                "common_python_tasks.utils.should_publish_github_release",
                return_value=True,
            ),
            patch(
                "common_python_tasks.utils.get_github_repository",
                return_value="ci-sourcerer/common-python-tasks",
            ),
            patch("common_python_tasks.utils.get_github_token", return_value="token"),
            patch(
                "common_python_tasks.utils.get_github_release_asset_paths",
                return_value=[],
            ),
            patch(
                "common_python_tasks.utils.urllib.request.urlopen",
                side_effect=urlopen_side_effect,
            ),
        ):
            result = publish_github_release(
                "v1.2.3",
                release_name="v1.2.3",
                body="Updated",
                prerelease=True,
            )

        assert result == {"id": 321, "tag_name": "v1.2.3", "body": "Updated"}
        assert [request["method"] for request in requests] == ["GET", "PATCH"]
        assert json.loads(requests[1]["data"].decode("utf-8")) == {
            "tag_name": "v1.2.3",
            "name": "v1.2.3",
            "body": "Updated",
            "draft": False,
            "prerelease": True,
        }

    def test_publish_github_release_skips_when_disabled(self):
        from common_python_tasks.tasks import publish_github_release

        with (
            patch(
                "common_python_tasks.utils.should_publish_github_release",
                return_value=False,
            ),
            patch("common_python_tasks.utils.get_github_repository") as mock_repository,
            patch("common_python_tasks.utils.get_github_token") as mock_token,
            patch("common_python_tasks.utils.urllib.request.urlopen") as mock_urlopen,
        ):
            assert publish_github_release("v1.2.3") is None

        mock_repository.assert_not_called()
        mock_token.assert_not_called()
        mock_urlopen.assert_not_called()
