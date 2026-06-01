import importlib
import json
import os
from pathlib import Path
from unittest.mock import ANY, MagicMock, call, patch

import pytest


def _release_run_command_side_effect(changelog_status: str = " M CHANGELOG.md\n"):
    def side_effect(
        command,
        capture_output=False,
        acceptable_returncodes=None,
        env=None,
        always_show_command=False,
        dry_run=False,
    ):
        if command[:3] == ["git", "status", "--porcelain"]:
            return MagicMock(returncode=0, stdout=changelog_status)
        return MagicMock(returncode=0, stdout="")

    return side_effect


def test_format_all_uses_run_available_tools(mock_find_spec):
    from common_python_tasks.tasks import format_all
    from common_python_tasks.utils import is_package_installed

    is_package_installed.cache_clear()
    mock_find_spec.return_value = MagicMock()

    with patch("common_python_tasks.utils.run_command") as mock_cmd:
        format_all()

        assert mock_cmd.call_count == 3


def test_lint_all_uses_run_available_tools(mock_find_spec):
    from common_python_tasks.tasks import lint_all
    from common_python_tasks.utils import is_package_installed

    is_package_installed.cache_clear()
    mock_find_spec.return_value = MagicMock()

    with patch("common_python_tasks.utils.run_command") as mock_cmd:
        with patch("common_python_tasks.utils.get_config_path") as mock_config:
            mock_config.return_value = ".flake8"
            lint_all()

        assert mock_cmd.call_count == 4


def test_format_all_fails_when_no_tools_installed(mock_find_spec):
    from common_python_tasks.tasks import format_all
    from common_python_tasks.utils import is_package_installed

    is_package_installed.cache_clear()
    mock_find_spec.return_value = None

    with patch("common_python_tasks.utils.LOGGER"):
        with pytest.raises(SystemExit) as exc_info:
            format_all()

        assert exc_info.value.code == 1


def test_confirm_loops_until_valid_response():
    from common_python_tasks.tasks import _confirm

    with patch("builtins.input", side_effect=["maybe", "Y"]):
        assert _confirm("Proceed?") is True

    with patch("builtins.input", side_effect=["", "no"]):
        assert _confirm("Proceed?") is False


def test_lint_all_fails_when_no_tools_installed(mock_find_spec):
    from common_python_tasks.tasks import lint_all
    from common_python_tasks.utils import is_package_installed

    is_package_installed.cache_clear()
    mock_find_spec.return_value = None

    with patch("common_python_tasks.utils.LOGGER"):
        with pytest.raises(SystemExit) as exc_info:
            lint_all()

        assert exc_info.value.code == 1


def test_print_available_tasks_includes_docstrings(capsys):
    from common_python_tasks.__main__ import print_available_tasks

    print_available_tasks(internal=False, include_docs=True)
    captured = capsys.readouterr()

    assert " - test" in captured.out
    assert "Run the test suite with coverage" in captured.out
    assert "Bump the project version." in captured.out
    assert "Args:" not in captured.out


def test_get_task_tags_excludes_synthetic_task_prefix_tags():
    from common_python_tasks.__main__ import get_task_tags

    assert get_task_tags("format") == ["common", "format"]


def test_get_task_tags_returns_none_for_unknown_task():
    from common_python_tasks.__main__ import get_task_tags

    assert get_task_tags("non-existent-task") is None


def test_clean_dist_only_removes_only_dist(tmp_path, monkeypatch):
    from common_python_tasks.tasks import clean

    monkeypatch.chdir(tmp_path)
    (tmp_path / "dist").mkdir()
    (tmp_path / ".pytest_cache").mkdir()
    (tmp_path / "foo.pyc").write_text("x")

    clean(dist_only=True)

    assert not (tmp_path / "dist").exists()
    assert (tmp_path / ".pytest_cache").exists()
    assert (tmp_path / "foo.pyc").exists()


def test_public_tasks_defaults_to_common_profile():
    import common_python_tasks

    common_python_tasks = importlib.reload(common_python_tasks)
    task_map = common_python_tasks.tasks()["tasks"]

    assert "format" in task_map
    assert "build-image" not in task_map
    assert "stack-up" not in task_map
    assert task_map["release"]["script"].endswith(":release_without_containers")


def test_public_tasks_supports_explicit_empty_include_for_all_tasks():
    import common_python_tasks

    common_python_tasks = importlib.reload(common_python_tasks)
    task_map = common_python_tasks.tasks(include_tags=())["tasks"]

    assert "build-image" in task_map
    assert "stack-up" in task_map


def test_task_decorator_does_not_log_top_level_task(caplog):
    import logging

    tasks_module = importlib.import_module("common_python_tasks.tasks")

    caplog.set_level(logging.INFO, logger="common_python_tasks")

    @tasks_module.tasks.script(task_name="top-level-task", tags=())
    def top_level_task():
        return "ok"

    top_level_task()

    assert "Running task top-level-task" not in caplog.text


def test_task_decorator_logs_nested_task_only(caplog):
    import logging

    tasks_module = importlib.import_module("common_python_tasks.tasks")

    caplog.set_level(logging.INFO, logger="common_python_tasks")

    @tasks_module.tasks.script(task_name="inner-task", tags=())
    def inner_task():
        return "inner"

    @tasks_module.tasks.script(task_name="outer-task", tags=())
    def outer_task():
        inner_task()

    outer_task()

    assert "Running task outer-task" not in caplog.text
    assert "Running task inner-task" in caplog.text


class TestBumpVersion:
    @pytest.fixture
    def tag_calls(self):
        return []

    @pytest.fixture
    def mock_clean_repo_no_tags(self, tag_calls):
        with patch("common_python_tasks.git.get_dirty_files") as mock_dirty:
            with patch("common_python_tasks.git.ensure_on_default_branch"):
                with patch(
                    "common_python_tasks.project.get_project_version_from_poetry",
                    return_value="0.0.0",
                ):
                    with patch("common_python_tasks.utils.run_command") as mock_run:
                        mock_dirty.return_value = []

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
        with patch("common_python_tasks.git.get_dirty_files") as mock_dirty:
            with patch("common_python_tasks.git.ensure_on_default_branch"):
                with patch(
                    "common_python_tasks.project.get_project_version_from_poetry",
                    return_value="1.2.3",
                ):
                    with patch("common_python_tasks.utils.run_command") as mock_run:
                        mock_dirty.return_value = []

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

    def test_bump_patch_with_existing_tag(self, mock_clean_repo_with_tag, tag_calls):
        from common_python_tasks.tasks import bump_version

        bump_version("patch")
        assert tag_calls[-1] == "v1.2.4"

    def test_bump_version_defaults_to_auto(self, mock_clean_repo_with_tag, tag_calls):
        from common_python_tasks.git import ReleaseComponent
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
                "common_python_tasks.git.infer_bump_component_from_git_cliff",
                return_value=ReleaseComponent.MINOR,
            ),
            patch(
                "common_python_tasks.utils.run_command",
                side_effect=run_command_side_effect,
            ),
        ):
            bump_version()

        assert tag_calls[-1] == "v1.3.0"

    def test_bump_version_auto_for_pre_production_uses_git_cliff_inference(
        self, tag_calls
    ):
        from common_python_tasks.git import ReleaseComponent
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
            patch("common_python_tasks.git.ensure_on_default_branch"),
            patch(
                "common_python_tasks.git.infer_bump_component_from_git_cliff",
                return_value=ReleaseComponent.MAJOR,
            ),
            patch(
                "common_python_tasks.project.get_project_version_from_poetry",
                return_value="0.2.5",
            ),
            patch(
                "common_python_tasks.git.get_dirty_files",
                return_value=[],
            ),
            patch(
                "common_python_tasks.utils.run_command",
                side_effect=run_command_side_effect,
            ),
        ):
            bump_version()

        assert tag_calls[-1] == "v1.0.0"

    def test_bump_version_requires_default_branch(self, tag_calls):
        from common_python_tasks.tasks import bump_version

        with (
            patch(
                "common_python_tasks.git.ensure_on_default_branch",
                side_effect=SystemExit(1),
            ),
            patch(
                "common_python_tasks.project.get_project_version_from_poetry",
                return_value="0.2.5",
            ),
            patch(
                "common_python_tasks.git.get_dirty_files",
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

    def test_bump_with_stage_param(self, mock_clean_repo_with_tag, tag_calls):
        from common_python_tasks.tasks import bump_version

        bump_version("patch", stage="alpha")
        assert tag_calls[-1] == "v1.2.4a1"

    def test_dry_run_no_tags(self, mock_clean_repo_no_tags, tag_calls):
        from common_python_tasks.tasks import bump_version

        with patch("common_python_tasks.utils.LOGGER") as mock_logger:
            bump_version("patch", dry_run=True)
            mock_logger.info.assert_called_with(
                "\033[93m[DRY RUN]\033[0m Would bump version to %s",
                "0.0.1",
            )
            assert len(tag_calls) == 0

    def test_dry_run_with_existing_tag(self, mock_clean_repo_with_tag, tag_calls):
        from common_python_tasks.tasks import bump_version

        with patch("common_python_tasks.utils.LOGGER") as mock_logger:
            bump_version("minor", stage="alpha", dry_run=True)
            mock_logger.info.assert_called_with(
                "\033[93m[DRY RUN]\033[0m Would bump version to %s",
                "1.3.0a1",
            )
            assert len(tag_calls) == 0

    def test_invalid_component_fails(self):
        from common_python_tasks.tasks import bump_version

        with (
            patch("common_python_tasks.git.ensure_on_default_branch"),
            patch("common_python_tasks.git.get_dirty_files") as mock_dirty,
        ):
            mock_dirty.return_value = []
            with patch("common_python_tasks.utils.LOGGER"):
                with pytest.raises(SystemExit) as exc_info:
                    bump_version("invalid")
                assert exc_info.value.code == 1

    def test_invalid_stage_fails(self):
        from common_python_tasks.tasks import bump_version

        with (
            patch("common_python_tasks.git.ensure_on_default_branch"),
            patch("common_python_tasks.git.get_dirty_files") as mock_dirty,
        ):
            mock_dirty.return_value = []
            with patch("common_python_tasks.utils.LOGGER"):
                with pytest.raises(SystemExit) as exc_info:
                    bump_version("patch", stage="invalid")
                assert exc_info.value.code == 1

    def test_dirty_repo_fails(self):
        from common_python_tasks.tasks import bump_version

        with (
            patch("common_python_tasks.git.ensure_on_default_branch"),
            patch("common_python_tasks.git.get_dirty_files") as mock_dirty,
        ):
            mock_dirty.return_value = ["modified_file.py"]
            with patch("common_python_tasks.utils.LOGGER"):
                with pytest.raises(SystemExit) as exc_info:
                    bump_version("patch")
                assert exc_info.value.code == 1

    def test_dirty_repo_can_be_allowed(self):
        from common_python_tasks.tasks import bump_version

        with (
            patch("common_python_tasks.git.ensure_on_default_branch"),
            patch("common_python_tasks.git.get_dirty_files") as mock_dirty,
            patch(
                "common_python_tasks.git.compute_next_release_version"
            ) as mock_compute,
            patch("common_python_tasks.utils.run_command") as mock_run_command,
        ):
            mock_dirty.return_value = [Path("modified_file.py")]
            mock_compute.return_value = MagicMock(version="1.2.3")

            bump_version("patch", allow_dirty=True)

            mock_run_command.assert_called_once_with(["git", "tag", "v1.2.3"])

    def test_release_runs_container_steps(self):
        from common_python_tasks.tasks import release

        with (
            patch.dict(
                os.environ, {"RELEASE_PRE_SCRIPT": "", "RELEASE_POST_SCRIPT": ""}
            ),
            patch("common_python_tasks.git.ensure_on_default_branch"),
            patch("common_python_tasks.git.get_dirty_files", return_value=[]),
            patch("common_python_tasks.tasks.clean") as mock_clean,
            patch("common_python_tasks.tasks.bump_version") as mock_bump,
            patch(
                "common_python_tasks.utils.prepend_changelog"
            ) as mock_prepend_changelog,
            patch("common_python_tasks.utils.run_command") as mock_run_command,
            patch("common_python_tasks.tasks.build_package") as mock_build_package,
            patch("common_python_tasks.tasks.publish_package") as mock_publish,
            patch(
                "common_python_tasks.project.get_project_version_from_poetry",
                return_value="1.2.2",
            ),
            patch("common_python_tasks.docker.build_image") as mock_build_image,
            patch("common_python_tasks.tasks.push_image") as mock_push_image,
            patch(
                "common_python_tasks.github.get_github_release_asset_paths",
                return_value=[],
            ),
            patch(
                "common_python_tasks.github.publish_github_release"
            ) as mock_publish_github_release,
        ):
            mock_run_command.side_effect = _release_run_command_side_effect()

            release(
                "patch",
                debug=True,
                no_cache=True,
                plain=True,
                single_arch=True,
            )

            mock_clean.assert_called_once_with()
            mock_bump.assert_called_once_with(
                component="patch", stage=None, dry_run=False, allow_dirty=False
            )
            mock_prepend_changelog.assert_called_once_with(
                "v1.2.3", Path("CHANGELOG.md")
            )
            mock_run_command.assert_has_calls(
                [
                    call(
                        ["git", "status", "--porcelain", "--", Path("CHANGELOG.md")],
                        capture_output=True,
                    ),
                    call(["git", "add", Path("CHANGELOG.md")]),
                    call(
                        [
                            "git",
                            "commit",
                            "-m",
                            "chore(release): update changelog for v1.2.3",
                        ]
                    ),
                    call(["git", "push", "origin", "HEAD"]),
                    call(["git", "push", "origin", "v1.2.3"]),
                ]
            )
            mock_build_package.assert_called_once_with(clean_dist=True)
            mock_publish.assert_called_once_with(build_first=False)
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
                release_name="v1.2.3",
                body=None,
                prerelease=False,
                draft=False,
                assets=[],
            )

    def test_release_without_containers_runs_pre_and_post_scripts(self):
        from common_python_tasks.tasks import release_without_containers

        with (
            patch("common_python_tasks.git.ensure_on_default_branch"),
            patch("common_python_tasks.git.get_dirty_files", return_value=[]),
            patch("common_python_tasks.tasks.clean") as mock_clean,
            patch("common_python_tasks.tasks.bump_version") as mock_bump,
            patch("common_python_tasks.tasks.build_package"),
            patch("common_python_tasks.tasks.publish_package"),
            patch("common_python_tasks.utils.prepend_changelog"),
            patch("common_python_tasks.utils.run_command") as mock_run_command,
            patch(
                "common_python_tasks.project.get_project_version_from_poetry",
                return_value="0.0.1",
            ),
            patch(
                "common_python_tasks.github.get_github_release_asset_paths",
                return_value=[],
            ),
            patch("common_python_tasks.github.publish_github_release"),
        ):
            release_without_containers(
                component="patch",
                pre_script="echo pre",
                post_script="echo post",
            )

            mock_clean.assert_called_once_with()
            mock_bump.assert_called_once_with(
                component="patch", stage=None, dry_run=False, allow_dirty=False
            )
            mock_run_command.assert_any_call(
                ["git", "push", "origin", "v0.0.2"],
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
            assert first_hook_env["RELEASE_SCRIPT_DRY_RUN"] == "0"

    def test_release_without_containers_uses_phase_configured_release_script_hooks(
        self,
    ):
        from common_python_tasks.tasks import release_without_containers

        pre_script = "RELEASE_SCRIPT_PHASE=pre python scripts/release_script.py"
        post_script = "RELEASE_SCRIPT_PHASE=post python scripts/release_script.py"

        with (
            patch.dict(
                os.environ,
                {"RELEASE_PRE_SCRIPT": pre_script, "RELEASE_POST_SCRIPT": post_script},
            ),
            patch("common_python_tasks.git.ensure_on_default_branch"),
            patch("common_python_tasks.git.get_dirty_files", return_value=[]),
            patch("common_python_tasks.tasks.clean"),
            patch("common_python_tasks.tasks.bump_version"),
            patch("common_python_tasks.tasks.build_package"),
            patch("common_python_tasks.tasks.publish_package"),
            patch("common_python_tasks.utils.prepend_changelog"),
            patch("common_python_tasks.utils.run_command") as mock_run_command,
            patch(
                "common_python_tasks.project.get_project_version_from_poetry",
                return_value="0.0.1",
            ),
            patch(
                "common_python_tasks.github.get_github_release_asset_paths",
                return_value=[],
            ),
            patch("common_python_tasks.github.publish_github_release"),
        ):
            release_without_containers(component="patch")

            mock_run_command.assert_any_call(
                ["sh", "-lc", pre_script],
                env=ANY,
                dry_run=False,
            )
            mock_run_command.assert_any_call(
                ["sh", "-lc", post_script],
                env=ANY,
                dry_run=False,
            )

            pre_call = next(
                call_args
                for call_args in mock_run_command.call_args_list
                if call_args.args[0] == ["sh", "-lc", pre_script]
            )
            assert pre_call.kwargs["env"]["RELEASE_VERSION"] == "0.0.2"
            assert pre_call.kwargs["env"]["RELEASE_TAG"] == "v0.0.2"

    def test_release_dry_run_executes_hook_scripts_with_release_script_dry_run_env(
        self,
    ):
        from common_python_tasks.tasks import release_without_containers

        with (
            patch("common_python_tasks.git.ensure_on_default_branch"),
            patch("common_python_tasks.git.get_dirty_files", return_value=[]),
            patch("common_python_tasks.tasks.clean"),
            patch("common_python_tasks.tasks.bump_version"),
            patch("common_python_tasks.tasks.build_package"),
            patch("common_python_tasks.tasks.publish_package"),
            patch("common_python_tasks.utils.run_command") as mock_run_command,
            patch("common_python_tasks.utils.LOGGER"),
            patch(
                "common_python_tasks.project.get_project_version_from_poetry",
                return_value="0.0.1",
            ),
            patch(
                "common_python_tasks.github.get_github_release_asset_paths",
                return_value=[],
            ),
            patch("common_python_tasks.github.publish_github_release"),
        ):
            release_without_containers(
                component="patch",
                dry_run=True,
                pre_script="echo pre",
                post_script="echo post",
            )

            pre_call = next(
                call_args
                for call_args in mock_run_command.call_args_list
                if call_args.args[0] == ["sh", "-lc", "echo pre"]
            )
            assert pre_call.kwargs["dry_run"] is False
            assert pre_call.kwargs["env"]["RELEASE_SCRIPT_DRY_RUN"] == "1"
            assert pre_call.kwargs["env"]["RELEASE_DRY_RUN"] == "1"

            post_call = next(
                call_args
                for call_args in mock_run_command.call_args_list
                if call_args.args[0] == ["sh", "-lc", "echo post"]
            )
            assert post_call.kwargs["dry_run"] is False
            assert post_call.kwargs["env"]["RELEASE_SCRIPT_DRY_RUN"] == "1"

    def test_release_dry_run_only_bumps_version(self):
        from common_python_tasks.tasks import release

        with (
            patch("common_python_tasks.git.ensure_on_default_branch"),
            patch("common_python_tasks.git.get_dirty_files", return_value=[]),
            patch("common_python_tasks.tasks.clean") as mock_clean,
            patch("common_python_tasks.tasks.bump_version") as mock_bump,
            patch("common_python_tasks.tasks.build_package") as mock_build_package,
            patch("common_python_tasks.tasks.publish_package") as mock_publish,
            patch(
                "common_python_tasks.project.get_project_version_from_poetry",
                return_value="1.2.2",
            ),
            patch(
                "common_python_tasks.github.get_github_release_asset_paths",
                return_value=[],
            ),
            patch(
                "common_python_tasks.utils.get_prepended_changelog_contents",
                return_value="## [1.2.3] - 2026-05-22\n\n# Changelog\n",
            ),
            patch("common_python_tasks.docker.build_image") as mock_build_image,
            patch("common_python_tasks.tasks.push_image") as mock_push_image,
            patch("common_python_tasks.utils.LOGGER") as mock_logger,
            patch("common_python_tasks.tasks.LOGGER") as mock_tasks_logger,
            patch(
                "common_python_tasks.github.publish_github_release"
            ) as mock_publish_github_release,
            patch("common_python_tasks.utils.run_command") as mock_run_command,
        ):
            release(component="patch", dry_run=True)

            mock_clean.assert_not_called()
            mock_bump.assert_called_once_with(
                component="patch", stage=None, dry_run=True, allow_dirty=True
            )
            mock_build_package.assert_not_called()
            mock_publish.assert_not_called()
            mock_build_image.assert_not_called()
            mock_push_image.assert_not_called()
            mock_publish_github_release.assert_not_called()
            mock_logger.info.assert_any_call(
                "\033[93m[DRY RUN]\033[0m Would clean generated artifacts before release"
            )
            mock_logger.info.assert_any_call(
                "\033[93m[DRY RUN]\033[0m Would prepend generated git-cliff release notes for %s to %s",
                "v1.2.3",
                Path("CHANGELOG.md"),
            )
            mock_tasks_logger.debug.assert_any_call(
                "Dry-run rendered %s contents:\n%s",
                Path("CHANGELOG.md"),
                "## [1.2.3] - 2026-05-22\n\n# Changelog\n",
            )
            mock_run_command.assert_any_call(
                ["git", "add", Path("CHANGELOG.md")],
                dry_run=True,
            )
            mock_run_command.assert_any_call(
                [
                    "git",
                    "commit",
                    "-m",
                    "chore(release): update changelog for v1.2.3",
                ],
                dry_run=True,
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
            mock_logger.info.assert_any_call(
                "\033[93m[DRY RUN]\033[0m Would publish GitHub Release %s with built assets",
                "v1.2.3",
            )

    def test_release_without_containers_accepts_none_stage_string(self):
        from common_python_tasks.tasks import release_without_containers

        with (
            patch.dict(
                os.environ, {"RELEASE_PRE_SCRIPT": "", "RELEASE_POST_SCRIPT": ""}
            ),
            patch("common_python_tasks.git.ensure_on_default_branch"),
            patch("common_python_tasks.git.get_dirty_files", return_value=[]),
            patch("common_python_tasks.tasks.clean") as mock_clean,
            patch("common_python_tasks.tasks.bump_version") as mock_bump,
            patch(
                "common_python_tasks.utils.prepend_changelog"
            ) as mock_prepend_changelog,
            patch("common_python_tasks.utils.run_command") as mock_run_command,
            patch("common_python_tasks.tasks.build_package") as mock_build_package,
            patch("common_python_tasks.tasks.publish_package") as mock_publish,
            patch(
                "common_python_tasks.project.get_project_version_from_poetry",
                return_value="1.2.2",
            ),
            patch(
                "common_python_tasks.github.get_github_release_asset_paths",
                return_value=[],
            ),
            patch(
                "common_python_tasks.github.publish_github_release"
            ) as mock_publish_github_release,
        ):
            mock_run_command.side_effect = _release_run_command_side_effect()

            release_without_containers(component="patch", stage="none")

            mock_clean.assert_called_once_with()
            mock_bump.assert_called_once_with(
                component="patch", stage=None, dry_run=False, allow_dirty=False
            )
            mock_prepend_changelog.assert_called_once_with(
                "v1.2.3", Path("CHANGELOG.md")
            )
            mock_run_command.assert_has_calls(
                [
                    call(
                        ["git", "status", "--porcelain", "--", Path("CHANGELOG.md")],
                        capture_output=True,
                    ),
                    call(["git", "add", Path("CHANGELOG.md")]),
                    call(
                        [
                            "git",
                            "commit",
                            "-m",
                            "chore(release): update changelog for v1.2.3",
                        ]
                    ),
                    call(["git", "push", "origin", "HEAD"]),
                    call(["git", "push", "origin", "v1.2.3"]),
                ]
            )
            mock_build_package.assert_called_once_with(clean_dist=True)
            mock_publish.assert_called_once_with(build_first=False)
            mock_publish_github_release.assert_called_once_with(
                "v1.2.3",
                release_name="v1.2.3",
                body=None,
                prerelease=False,
                draft=False,
                assets=[],
            )

    def test_release_without_containers_can_disable_changelog_updates(self):
        from common_python_tasks.tasks import release_without_containers

        with (
            patch.dict(
                os.environ,
                {
                    "RELEASE_PRE_SCRIPT": "",
                    "RELEASE_POST_SCRIPT": "",
                    "RELEASE_UPDATE_CHANGELOG": "0",
                },
            ),
            patch("common_python_tasks.git.ensure_on_default_branch"),
            patch("common_python_tasks.git.get_dirty_files", return_value=[]),
            patch("common_python_tasks.tasks.clean") as mock_clean,
            patch("common_python_tasks.tasks.bump_version") as mock_bump,
            patch("common_python_tasks.utils.run_command") as mock_run_command,
            patch("common_python_tasks.tasks.build_package") as mock_build_package,
            patch("common_python_tasks.tasks.publish_package") as mock_publish,
            patch(
                "common_python_tasks.project.get_project_version_from_poetry",
                return_value="1.2.2",
            ),
            patch(
                "common_python_tasks.github.get_github_release_asset_paths",
                return_value=[],
            ),
            patch("common_python_tasks.github.publish_github_release"),
        ):
            release_without_containers(component="patch")

            mock_clean.assert_called_once_with()
            mock_bump.assert_called_once_with(
                component="patch", stage=None, dry_run=False, allow_dirty=False
            )
            mock_run_command.assert_has_calls(
                [
                    call(["git", "push", "origin", "HEAD"]),
                    call(["git", "push", "origin", "v1.2.3"]),
                ]
            )
            mock_build_package.assert_called_once_with(clean_dist=True)
            mock_publish.assert_called_once_with(build_first=False)

    def test_release_without_containers_prompts_once_for_dirty_repo(self):
        from common_python_tasks.tasks import release_without_containers

        with (
            patch.dict(
                os.environ,
                {
                    "RELEASE_PRE_SCRIPT": "",
                    "RELEASE_POST_SCRIPT": "",
                    "RELEASE_UPDATE_CHANGELOG": "0",
                },
            ),
            patch("common_python_tasks.git.ensure_on_default_branch"),
            patch(
                "common_python_tasks.git.get_dirty_files",
                return_value=[Path("README.md")],
            ),
            patch("builtins.input", return_value="y") as mock_input,
            patch("common_python_tasks.tasks.clean") as mock_clean,
            patch("common_python_tasks.tasks.bump_version") as mock_bump,
            patch("common_python_tasks.utils.run_command") as mock_run_command,
            patch("common_python_tasks.tasks.build_package") as mock_build_package,
            patch("common_python_tasks.tasks.publish_package") as mock_publish,
            patch(
                "common_python_tasks.project.get_project_version_from_poetry",
                return_value="1.2.2",
            ),
            patch(
                "common_python_tasks.github.get_github_release_asset_paths",
                return_value=[],
            ),
            patch("common_python_tasks.github.publish_github_release"),
        ):
            release_without_containers(component="patch")

            mock_input.assert_called_once_with("Proceed with release anyway? [y/N]: ")
            mock_clean.assert_called_once_with()
            mock_bump.assert_called_once_with(
                component="patch", stage=None, dry_run=False, allow_dirty=True
            )
            mock_run_command.assert_has_calls(
                [
                    call(["git", "push", "origin", "HEAD"]),
                    call(["git", "push", "origin", "v1.2.3"]),
                ]
            )
            mock_build_package.assert_called_once_with(clean_dist=True)
            mock_publish.assert_called_once_with(build_first=False)

    def test_release_without_containers_allows_dirty_repo_without_prompt_env(self):
        from common_python_tasks.tasks import release_without_containers

        with (
            patch.dict(
                os.environ,
                {
                    "RELEASE_PRE_SCRIPT": "echo pre",
                    "RELEASE_POST_SCRIPT": "",
                    "RELEASE_UPDATE_CHANGELOG": "0",
                    "COMMON_PYTHON_TASKS_NO_PROMPT": "1",
                },
            ),
            patch("common_python_tasks.git.ensure_on_default_branch"),
            patch(
                "common_python_tasks.git.get_dirty_files",
                return_value=[Path("README.md")],
            ),
            patch("builtins.input") as mock_input,
            patch("common_python_tasks.tasks.clean"),
            patch("common_python_tasks.tasks.bump_version") as mock_bump,
            patch("common_python_tasks.utils.run_command") as mock_run_command,
            patch("common_python_tasks.tasks.build_package"),
            patch("common_python_tasks.tasks.publish_package"),
            patch(
                "common_python_tasks.project.get_project_version_from_poetry",
                return_value="1.2.2",
            ),
            patch(
                "common_python_tasks.github.get_github_release_asset_paths",
                return_value=[],
            ),
            patch("common_python_tasks.github.publish_github_release"),
        ):
            release_without_containers(component="patch")

            mock_input.assert_not_called()
            mock_bump.assert_called_once_with(
                component="patch", stage=None, dry_run=False, allow_dirty=True
            )
            pre_call = next(
                call_args
                for call_args in mock_run_command.call_args_list
                if call_args.args[0] == ["sh", "-lc", "echo pre"]
            )
            assert pre_call.kwargs["env"]["COMMON_PYTHON_TASKS_NO_PROMPT"] == "1"

    def test_release_without_containers_fails_when_not_on_default_branch(self):
        from common_python_tasks.tasks import release_without_containers

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
                release_without_containers()

        assert exc_info.value.code == 1


class TestGitHubReleasePublishing:
    def test_publish_github_release_creates_release_when_missing(self):
        from common_python_tasks.tasks import publish_github_release

        requests = []

        class FakeResponse:
            def __init__(self, status_code: int, payload: dict[str, object]):
                self.status_code = status_code
                self._payload = payload

            @property
            def text(self):
                return json.dumps(self._payload)

            def json(self):
                return self._payload

            def raise_for_status(self):
                return None

        def request_side_effect(method, url, data=None, headers=None, timeout=30):
            requests.append(
                {
                    "method": method,
                    "url": url,
                    "data": data,
                }
            )
            if method == "GET":
                return FakeResponse(404, {"message": "Not Found"})
            return FakeResponse(200, {"id": 123, "tag_name": "v1.2.3"})

        with (
            patch(
                "common_python_tasks.github.should_publish_github_release",
                return_value=True,
            ),
            patch(
                "common_python_tasks.github.get_github_repository",
                return_value="ci-sourcerer/common-python-tasks",
            ),
            patch("common_python_tasks.github.get_github_token", return_value="token"),
            patch(
                "common_python_tasks.github.get_github_release_asset_paths",
                return_value=[],
            ) as mock_get_assets,
            patch(
                "common_python_tasks.github.requests.request",
                side_effect=request_side_effect,
            ),
        ):
            result = publish_github_release(
                "v1.2.3",
                release_name="v1.2.3",
                body="Release v1.2.3",
                assets=["dist/*.whl"],
            )

        assert result == {"id": 123, "tag_name": "v1.2.3"}
        mock_get_assets.assert_called_once_with(["dist/*.whl"])
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
            def __init__(self, status_code: int, payload: dict[str, object]):
                self.status_code = status_code
                self._payload = payload

            @property
            def text(self):
                return json.dumps(self._payload)

            def json(self):
                return self._payload

            def raise_for_status(self):
                return None

        def request_side_effect(method, url, data=None, headers=None, timeout=30):
            requests.append(
                {
                    "method": method,
                    "url": url,
                    "data": data,
                }
            )
            if method == "GET":
                return FakeResponse(404, {"message": "Not Found"})
            return FakeResponse(200, {"id": 123, "tag_name": "v1.2.3"})

        with (
            patch(
                "common_python_tasks.github.should_publish_github_release",
                return_value=True,
            ),
            patch(
                "common_python_tasks.github.get_github_repository",
                return_value="ci-sourcerer/common-python-tasks",
            ),
            patch("common_python_tasks.github.get_github_token", return_value="token"),
            patch("shutil.which", return_value="/usr/bin/git-cliff"),
            patch(
                "common_python_tasks.utils.run_command",
                return_value=MagicMock(stdout=changelog, returncode=0),
            ),
            patch(
                "common_python_tasks.github.get_github_release_asset_paths",
                return_value=[],
            ),
            patch(
                "common_python_tasks.github.requests.request",
                side_effect=request_side_effect,
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
            "body": "- Fix critical bug",
            "draft": False,
            "prerelease": False,
        }

    def test_publish_github_release_falls_back_to_latest_tagged_notes_when_unreleased_is_placeholder(
        self,
    ):
        from common_python_tasks.tasks import publish_github_release

        requests = []
        unreleased_placeholder = "[unreleased]\n"
        latest_tagged_notes = "## v1.2.3\n- Fix critical bug\n"

        class FakeResponse:
            def __init__(self, status_code: int, payload: dict[str, object]):
                self.status_code = status_code
                self._payload = payload

            @property
            def text(self):
                return json.dumps(self._payload)

            def json(self):
                return self._payload

            def raise_for_status(self):
                return None

        def request_side_effect(method, url, data=None, headers=None, timeout=30):
            requests.append(
                {
                    "method": method,
                    "url": url,
                    "data": data,
                }
            )
            if method == "GET":
                return FakeResponse(404, {"message": "Not Found"})
            return FakeResponse(200, {"id": 123, "tag_name": "v1.2.3"})

        with (
            patch(
                "common_python_tasks.github.should_publish_github_release",
                return_value=True,
            ),
            patch(
                "common_python_tasks.github.get_github_repository",
                return_value="ci-sourcerer/common-python-tasks",
            ),
            patch("common_python_tasks.github.get_github_token", return_value="token"),
            patch(
                "common_python_tasks.utils.run_command",
                side_effect=[
                    MagicMock(stdout=unreleased_placeholder, returncode=0),
                    MagicMock(stdout=latest_tagged_notes, returncode=0),
                ],
            ),
            patch(
                "common_python_tasks.github.get_github_release_asset_paths",
                return_value=[],
            ),
            patch(
                "common_python_tasks.github.requests.request",
                side_effect=request_side_effect,
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
            "body": latest_tagged_notes.strip(),
            "draft": False,
            "prerelease": False,
        }

    def test_publish_github_release_updates_existing_release(self):
        from common_python_tasks.tasks import publish_github_release

        requests = []

        class FakeResponse:
            def __init__(self, status_code: int, payload: dict[str, object]):
                self.status_code = status_code
                self._payload = payload

            @property
            def text(self):
                return json.dumps(self._payload)

            def json(self):
                return self._payload

            def raise_for_status(self):
                return None

        def request_side_effect(method, url, data=None, headers=None, timeout=30):
            requests.append(
                {
                    "method": method,
                    "url": url,
                    "data": data,
                }
            )
            if method == "GET":
                return FakeResponse(200, {"id": 321, "tag_name": "v1.2.3"})
            return FakeResponse(
                200, {"id": 321, "tag_name": "v1.2.3", "body": "Updated"}
            )

        with (
            patch(
                "common_python_tasks.github.should_publish_github_release",
                return_value=True,
            ),
            patch(
                "common_python_tasks.github.get_github_repository",
                return_value="ci-sourcerer/common-python-tasks",
            ),
            patch("common_python_tasks.github.get_github_token", return_value="token"),
            patch(
                "common_python_tasks.github.get_github_release_asset_paths",
                return_value=[],
            ),
            patch(
                "common_python_tasks.github.requests.request",
                side_effect=request_side_effect,
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
                "common_python_tasks.github.should_publish_github_release",
                return_value=False,
            ),
            patch(
                "common_python_tasks.github.get_github_repository"
            ) as mock_repository,
            patch("common_python_tasks.github.get_github_token") as mock_token,
            patch("common_python_tasks.github.requests.request") as mock_request,
        ):
            assert publish_github_release("v1.2.3") is None

        mock_repository.assert_not_called()
        mock_token.assert_not_called()
        mock_request.assert_not_called()


def test_build_with_containers_calls_task_build_image():
    from common_python_tasks.tasks import build

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
    from common_python_tasks.tasks import build

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
            build_args=["FOO=bar"],
            container_env=["X=1"],
            container_envfile=["env1.env", "env2.env"],
        )

    mock_build_package.assert_called_once_with()
    mock_build_image.assert_called_once_with(
        debug=True,
        no_cache=True,
        plain=True,
        single_arch=True,
        build_args=["FOO=bar"],
        container_env=["X=1"],
        container_envfile=["env1.env", "env2.env"],
    )


def test_build_without_containers_skips_task_build_image():
    from common_python_tasks.tasks import build

    with (
        patch("common_python_tasks.tasks.build_package") as mock_build_package,
        patch("common_python_tasks.tasks.build_image") as mock_build_image,
    ):
        build(has_containers=False)

    mock_build_package.assert_called_once_with()
    mock_build_image.assert_not_called()


def test_fastapi_stack_up_passes_container_build_options(
    temp_project_dir,
    mock_load_data_file,
    mock_run_command,
):
    from common_python_tasks.tasks import fastapi_stack_up

    build_image_calls: list[dict[str, object]] = []

    def fake_build_image(*args, **kwargs):
        build_image_calls.append(kwargs)
        return ("version", "commit")

    with (
        patch("common_python_tasks.docker.build_image", new=fake_build_image),
        patch(
            "common_python_tasks.env.load_container_env_tokens", return_value=["X=1"]
        ),
        patch(
            "common_python_tasks.docker_compose.ensure_secrets_generated"
        ) as mock_secrets,  # noqa: F841
        patch(
            "common_python_tasks.docker_compose.load_and_prepare_compose",
            return_value=([], [], [], {"API_PORT": "8080"}),
        ),
        patch("common_python_tasks.docker_compose.run_docker_compose_command"),
    ):
        fastapi_stack_up(
            detach=True,
            build_args=["FOO=bar"],
            container_env=["X=1"],
            container_envfile=["env1.env"],
        )

    assert len(build_image_calls) == 1
    assert build_image_calls[0]["build_args"] == ["FOO=bar"]
    assert build_image_calls[0]["container_env"] == ["X=1"]
    assert build_image_calls[0]["container_envfile"] == ["env1.env"]


def test_container_shell_selects_most_recent_tag(
    temp_project_dir,
    mock_run_command,
    mock_load_data_file,
    mock_get_package_name,
):
    """When `tag` is None, `container_shell` should pick the most-recently-built tag (no build)."""
    from common_python_tasks.tasks import container_shell

    run_calls: list[list[str]] = []
    original = mock_run_command.side_effect

    def tracking(command, *args, **kwargs):
        if len(command) >= 3 and command[:3] == ["docker", "image", "ls"]:
            result = original(command, *args, **kwargs)
            result.stdout = (
                "docker.io/test-package:abc123\n" "docker.io/test-package:1.0.0\n"
            )
            return result
        if "docker" in command and "run" in command:
            run_calls.append(command)
        return original(command, *args, **kwargs)

    mock_run_command.side_effect = tracking

    container_shell(no_echo_env=True)

    assert len(run_calls) == 1
    run_call = [str(part) for part in run_calls[0] if part is not None]

    assert "test-package:abc123" in " ".join(run_call)
    assert run_call[-2:] == [
        "-c",
        "$(command -v zsh || command -v fish || command -v ksh || command -v bash || command -v sh) || exit 127",
    ]


def test_run_container_passes_docker_runtime_options(
    temp_project_dir,
    mock_run_command,
    mock_get_package_name,
    monkeypatch,
):
    """`run_container` should forward env, envfile, privileged, and volumes to docker run."""
    from common_python_tasks import utils
    from common_python_tasks.tasks import run_container

    monkeypatch.setattr(utils, "get_full_image_name", lambda: "docker.io/test-package")

    run_calls: list[list[str]] = []
    original = mock_run_command.side_effect

    def tracking(command, *args, **kwargs):
        if len(command) >= 3 and command[:3] == ["docker", "image", "inspect"]:
            result = original(command, *args, **kwargs)
            result.returncode = 0
            return result
        if len(command) >= 2 and command[:2] == ["docker", "run"]:
            run_calls.append([str(part) for part in command if part is not None])
        return original(command, *args, **kwargs)

    mock_run_command.side_effect = tracking

    run_container(
        "custom-tag",
        entrypoint="/bin/sh",
        command="echo hi",
        root=True,
        echo_env=False,
        env=["FOO=bar", "BAZ"],
        envfile=[".env", ".env2"],
        privileged=True,
        volumes=["/tmp:/tmp", "/var/log:/var/log"],
    )

    assert len(run_calls) == 1
    run_call = run_calls[0]
    pairs = [run_call[i : i + 2] for i in range(len(run_call) - 1)]
    assert ["-e", "FOO=bar"] in pairs
    assert ["-e", "BAZ"] in pairs
    assert ["--env-file", ".env"] in pairs
    assert ["--env-file", ".env2"] in pairs
    assert ["-v", "/tmp:/tmp"] in pairs
    assert ["-v", "/var/log:/var/log"] in pairs
    assert "--privileged" in run_call
    assert run_call[-2:] == ["-c", "echo hi"]


def test_container_shell_forwards_docker_run_runtime_flags(
    temp_project_dir,
    mock_run_command,
    mock_get_package_name,
    monkeypatch,
):
    """`container_shell` should forward docker run env, envfile, privileged, and volumes options."""
    from common_python_tasks import utils
    from common_python_tasks.tasks import container_shell

    monkeypatch.setattr(utils, "get_full_image_name", lambda: "docker.io/test-package")

    run_calls: list[list[str]] = []
    original = mock_run_command.side_effect

    def tracking(command, *args, **kwargs):
        if len(command) >= 3 and command[:3] == ["docker", "image", "ls"]:
            result = original(command, *args, **kwargs)
            result.stdout = "docker.io/test-package:abc123\n"
            return result
        if len(command) >= 2 and command[:2] == ["docker", "run"]:
            run_calls.append([str(part) for part in command if part is not None])
        return original(command, *args, **kwargs)

    mock_run_command.side_effect = tracking

    container_shell(
        tag="custom",
        shell="bash",
        root=False,
        no_echo_env=True,
        env=["HELLO=WORLD"],
        envfile=["/tmp/envfile"],
        privileged=True,
        volumes=["/tmp:/tmp"],
    )

    assert len(run_calls) == 1
    run_call = run_calls[0]
    pairs = [run_call[i : i + 2] for i in range(len(run_call) - 1)]
    assert ["-e", "HELLO=WORLD"] in pairs
    assert ["--env-file", "/tmp/envfile"] in pairs
    assert ["-v", "/tmp:/tmp"] in pairs
    assert "--privileged" in run_call
    assert run_call[-2:] == ["-c", "$(command -v bash) || exit 127"]


def test_container_shell_wraps_fallback_shell_with_env_dump(
    temp_project_dir,
    mock_run_command,
    mock_load_data_file,
    mock_get_package_name,
):
    """`container_shell` should compose a shell fallback command that survives `echo_env=True`."""
    from common_python_tasks.tasks import container_shell

    run_calls: list[list[str | None]] = []
    original = mock_run_command.side_effect

    def tracking(command, *args, **kwargs):
        if len(command) >= 3 and command[:3] == ["docker", "image", "ls"]:
            result = original(command, *args, **kwargs)
            result.stdout = "docker.io/test-package:abc123\n"
            return result
        if "docker" in command and "run" in command:
            run_calls.append(command)
        return original(command, *args, **kwargs)

    mock_run_command.side_effect = tracking

    container_shell(no_echo_env=False)

    assert len(run_calls) == 1
    run_call = [str(part) for part in run_calls[0] if part is not None]
    assert run_call[-2] == "-c"
    assert (
        run_call[-1]
        == "echo '=== Container environment variables ===' && env | sort && echo '========================================' && exec $(command -v zsh || command -v fish || command -v ksh || command -v bash || command -v sh) || exit 127"
    )


def test_container_shell_fails_when_no_images(
    temp_project_dir,
    mock_run_command,
    mock_load_data_file,
    mock_get_package_name,
):
    """`container_shell` should exit when no built images exist and `tag` is None."""
    from common_python_tasks.tasks import container_shell

    original = mock_run_command.side_effect

    def tracking(command, *args, **kwargs):
        if len(command) >= 3 and command[:3] == ["docker", "image", "ls"]:
            result = original(command, *args, **kwargs)
            result.stdout = ""
            return result
        return original(command, *args, **kwargs)

    mock_run_command.side_effect = tracking

    with pytest.raises(SystemExit):
        container_shell()


def test_push_image_uses_full_registry_reference(monkeypatch):
    """`push_image` should push fully-qualified tags derived from full image name."""
    from common_python_tasks.tasks import push_image

    pushed_refs: list[str] = []

    with (
        patch(
            "common_python_tasks.utils.get_full_image_name",
            return_value="ghcr.io/acme/test-package",
        ),
        patch("common_python_tasks.git.get_image_tag", return_value="1.2.3"),
        patch("common_python_tasks.git.has_tags_later_in_history", return_value=False),
        patch("common_python_tasks.utils.run_command") as mock_run_command,
    ):

        def side_effect(command, *args, **kwargs):
            if command[:2] == ["docker", "push"]:
                pushed_refs.append(command[2])
            return MagicMock(returncode=0, stdout="")

        mock_run_command.side_effect = side_effect

        push_image(debug=False)

    assert pushed_refs == [
        "ghcr.io/acme/test-package:latest",
        "ghcr.io/acme/test-package:1.2.3",
    ]


def test_run_container_falls_back_to_full_image_reference_when_short_missing(
    mock_get_package_name,
):
    """`run_container` should inspect short then full references and run the available one."""
    from common_python_tasks.tasks import run_container

    inspect_calls: list[str] = []
    run_calls: list[list[str]] = []

    with (
        patch(
            "common_python_tasks.utils.get_full_image_name",
            return_value="ghcr.io/acme/test-package",
        ),
        patch("common_python_tasks.utils.run_command") as mock_run_command,
    ):

        def side_effect(command, *args, **kwargs):
            if command[:3] == ["docker", "image", "inspect"]:
                image_ref = command[3]
                inspect_calls.append(image_ref)
                return MagicMock(
                    returncode=(
                        0 if image_ref == "ghcr.io/acme/test-package:custom-tag" else 1
                    ),
                    stdout="",
                )

            if command[:2] == ["docker", "run"]:
                run_calls.append([str(part) for part in command if part is not None])

            return MagicMock(returncode=0, stdout="")

        mock_run_command.side_effect = side_effect

        run_container("custom-tag")

    assert inspect_calls == [
        "test-package:custom-tag",
        "ghcr.io/acme/test-package:custom-tag",
    ]
    assert len(run_calls) == 1
    assert run_calls[0][-1] == "ghcr.io/acme/test-package:custom-tag"
