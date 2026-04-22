import json
import urllib.error
from unittest.mock import ANY, MagicMock, patch

import pytest


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


def test_lint_all_fails_when_no_tools_installed(mock_find_spec):
    from common_python_tasks.tasks import lint_all
    from common_python_tasks.utils import is_package_installed

    is_package_installed.cache_clear()
    mock_find_spec.return_value = None

    with patch("common_python_tasks.utils.LOGGER"):
        with pytest.raises(SystemExit) as exc_info:
            lint_all()

        assert exc_info.value.code == 1


def test_task_decorator_does_not_log_top_level_task(caplog):
    import logging

    from common_python_tasks import tasks as tasks_module

    caplog.set_level(logging.INFO, logger="common_python_tasks")

    @tasks_module.tasks.script(task_name="top-level-task", tags=())
    def top_level_task():
        return "ok"

    top_level_task()

    assert "Running task top-level-task" not in caplog.text


def test_task_decorator_logs_nested_task_only(caplog):
    import logging

    from common_python_tasks import tasks as tasks_module

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
                "common_python_tasks.git.infer_bump_component_from_git_cliff",
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
            patch("common_python_tasks.git.ensure_on_default_branch"),
            patch(
                "common_python_tasks.git.infer_bump_component_from_git_cliff",
                return_value="major",
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

        assert tag_calls[-1] == "v0.2.6"

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
        from common_python_tasks.tasks import bump_version

        with (
            patch("common_python_tasks.git.ensure_on_default_branch"),
            patch("common_python_tasks.git.get_dirty_files") as mock_dirty,
        ):
            with patch(
                "common_python_tasks.project.get_project_version_from_poetry",
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


class TestReleaseTask:
    def test_release_runs_packaging_only_when_containers_excluded(self):
        from common_python_tasks.tasks import release

        with (
            patch("common_python_tasks.git.ensure_on_default_branch"),
            patch("common_python_tasks.tasks.clean") as mock_clean,
            patch("common_python_tasks.tasks.bump_version") as mock_bump,
            patch("common_python_tasks.utils.run_command") as mock_run_command,
            patch("common_python_tasks.tasks.build_package") as mock_build_package,
            patch("common_python_tasks.tasks.publish_package") as mock_publish,
            patch(
                "common_python_tasks.project.is_task_tag_included", return_value=False
            ) as mock_has_tag,
            patch(
                "common_python_tasks.project.get_project_version_from_poetry",
                return_value="1.2.2",
            ),
            patch("common_python_tasks.docker.build_image") as mock_build_image,
            patch("common_python_tasks.tasks.push_image") as mock_push_image,
            patch(
                "common_python_tasks.project.get_release_tag_from_poetry_version",
                return_value="v1.2.3",
            ),
            patch(
                "common_python_tasks.github.get_github_release_asset_paths",
                return_value=[],
            ),
            patch(
                "common_python_tasks.github.publish_github_release"
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
            patch("common_python_tasks.git.ensure_on_default_branch"),
            patch("common_python_tasks.tasks.clean") as mock_clean,
            patch("common_python_tasks.tasks.bump_version") as mock_bump,
            patch("common_python_tasks.utils.run_command") as mock_run_command,
            patch("common_python_tasks.tasks.build_package") as mock_build_package,
            patch("common_python_tasks.tasks.publish_package") as mock_publish,
            patch(
                "common_python_tasks.project.is_task_tag_included", return_value=True
            ) as mock_has_tag,
            patch(
                "common_python_tasks.project.get_project_version_from_poetry",
                return_value="1.2.2",
            ),
            patch("common_python_tasks.docker.build_image") as mock_build_image,
            patch("common_python_tasks.tasks.push_image") as mock_push_image,
            patch(
                "common_python_tasks.project.get_release_tag_from_poetry_version",
                return_value="v1.2.3",
            ),
            patch(
                "common_python_tasks.github.get_github_release_asset_paths",
                return_value=[],
            ),
            patch(
                "common_python_tasks.github.publish_github_release"
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
            patch("common_python_tasks.git.ensure_on_default_branch"),
            patch("common_python_tasks.tasks.clean") as mock_clean,
            patch("common_python_tasks.tasks.bump_version") as mock_bump,
            patch("common_python_tasks.tasks.build_package"),
            patch("common_python_tasks.tasks.publish_package"),
            patch("common_python_tasks.utils.run_command") as mock_run_command,
            patch(
                "common_python_tasks.project.is_task_tag_included",
                return_value=False,
            ),
            patch(
                "common_python_tasks.project.get_project_version_from_poetry",
                return_value="0.0.1",
            ),
            patch(
                "common_python_tasks.project.get_release_tag_from_poetry_version",
                return_value="v0.0.2",
            ),
            patch(
                "common_python_tasks.github.get_github_release_asset_paths",
                return_value=[],
            ),
            patch("common_python_tasks.github.publish_github_release"),
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

    def test_release_dry_run_only_bumps_version(self):
        from common_python_tasks.tasks import release

        with (
            patch("common_python_tasks.git.ensure_on_default_branch"),
            patch("common_python_tasks.tasks.clean") as mock_clean,
            patch("common_python_tasks.tasks.bump_version") as mock_bump,
            patch("common_python_tasks.tasks.build_package") as mock_build_package,
            patch("common_python_tasks.tasks.publish_package") as mock_publish,
            patch(
                "common_python_tasks.project.is_task_tag_included", return_value=True
            ) as mock_has_tag,
            patch(
                "common_python_tasks.project.get_project_version_from_poetry",
                return_value="1.2.2",
            ),
            patch(
                "common_python_tasks.project.get_release_tag_from_poetry_version",
                return_value="v1.2.2",
            ),
            patch(
                "common_python_tasks.github.get_github_release_asset_paths",
                return_value=[],
            ),
            patch("common_python_tasks.docker.build_image") as mock_build_image,
            patch("common_python_tasks.tasks.push_image") as mock_push_image,
            patch("common_python_tasks.utils.LOGGER") as mock_logger,
            patch(
                "common_python_tasks.github.publish_github_release"
            ) as mock_publish_github_release,
            patch("common_python_tasks.utils.run_command"),
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
            mock_logger.info.assert_any_call(
                "\033[93m[DRY RUN]\033[0m Would publish GitHub Release %s with assets=%s",
                "v1.2.2",
                [],
            )

    def test_release_accepts_none_stage_string(self):
        from common_python_tasks.tasks import release

        with (
            patch("common_python_tasks.git.ensure_on_default_branch"),
            patch("common_python_tasks.tasks.clean") as mock_clean,
            patch("common_python_tasks.tasks.bump_version") as mock_bump,
            patch("common_python_tasks.utils.run_command") as mock_run_command,
            patch("common_python_tasks.tasks.build_package") as mock_build_package,
            patch("common_python_tasks.tasks.publish_package") as mock_publish,
            patch(
                "common_python_tasks.project.is_task_tag_included", return_value=False
            ) as mock_has_tag,
            patch(
                "common_python_tasks.project.get_project_version_from_poetry",
                return_value="1.2.2",
            ),
            patch(
                "common_python_tasks.project.get_release_tag_from_poetry_version",
                return_value="v1.2.3",
            ),
            patch(
                "common_python_tasks.github.get_github_release_asset_paths",
                return_value=[],
            ),
            patch(
                "common_python_tasks.github.publish_github_release"
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
                "common_python_tasks.github.urllib.request.urlopen",
                side_effect=urlopen_side_effect,
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
                "common_python_tasks.github.urllib.request.urlopen",
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

    def test_publish_github_release_falls_back_to_latest_tagged_notes_when_unreleased_is_placeholder(
        self,
    ):
        from common_python_tasks.tasks import publish_github_release

        requests = []
        unreleased_placeholder = "[unreleased]\n"
        latest_tagged_notes = "## v1.2.3\n- Fix critical bug\n"

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
                "common_python_tasks.github.urllib.request.urlopen",
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
            "body": latest_tagged_notes.strip(),
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
                "common_python_tasks.github.urllib.request.urlopen",
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
                "common_python_tasks.github.should_publish_github_release",
                return_value=False,
            ),
            patch(
                "common_python_tasks.github.get_github_repository"
            ) as mock_repository,
            patch("common_python_tasks.github.get_github_token") as mock_token,
            patch("common_python_tasks.github.urllib.request.urlopen") as mock_urlopen,
        ):
            assert publish_github_release("v1.2.3") is None

        mock_repository.assert_not_called()
        mock_token.assert_not_called()
        mock_urlopen.assert_not_called()
