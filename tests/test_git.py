from unittest.mock import MagicMock, patch

import pytest


def test_infer_bump_component_from_git_cliff_returns_expected_bump():
    with (
        patch("shutil.which", return_value="/usr/bin/git-cliff"),
        patch(
            "common_python_tasks.utils.run_command",
            return_value=MagicMock(stdout="v2.0.0\n", returncode=0),
        ),
        patch(
            "common_python_tasks.project.get_project_version",
            return_value="1.3.2",
        ),
    ):
        from common_python_tasks.git import (
            ReleaseComponent,
            infer_bump_component_from_git_cliff,
        )

        assert infer_bump_component_from_git_cliff() == ReleaseComponent.MAJOR


class TestComputeNextReleaseVersion:
    def _call(self, component, stage=None, current_version="1.2.3"):
        with patch(
            "common_python_tasks.project.get_project_version",
            return_value=current_version,
        ):
            from common_python_tasks.git import (
                compute_next_release_version,
                parse_release_component,
                parse_release_stage,
            )

            parsed_component = component
            if isinstance(component, str):
                parsed_component = parse_release_component(component)

            parsed_stage = stage
            if isinstance(stage, str) or stage is None:
                parsed_stage = parse_release_stage(stage)

            return compute_next_release_version(parsed_component, parsed_stage)

    def test_patch_bump(self):
        result = self._call("patch")
        assert result.version == "1.2.4"
        assert result.component == "patch"

    def test_minor_bump(self):
        result = self._call("minor")
        assert result.version == "1.3.0"
        assert result.component == "minor"

    def test_major_bump(self):
        result = self._call("major")
        assert result.version == "2.0.0"
        assert result.component == "major"

    def test_alpha_stage(self):
        result = self._call("patch", stage="alpha")
        assert result.version == "1.2.4a1"

    def test_beta_stage(self):
        result = self._call("minor", stage="beta")
        assert result.version == "1.3.0b1"

    def test_rc_stage(self):
        result = self._call("major", stage="rc")
        assert result.version == "2.0.0rc1"

    def test_short_stage_alias_a(self):
        result = self._call("patch", stage="a")
        assert result.version == "1.2.4a1"

    def test_short_stage_alias_b(self):
        result = self._call("patch", stage="b")
        assert result.version == "1.2.4b1"

    def test_component_case_insensitive(self):
        result = self._call("PATCH")
        assert result.version == "1.2.4"
        assert result.component == "patch"

    def test_auto_delegates_to_git_cliff(self):
        from common_python_tasks.git import ReleaseComponent

        with (
            patch(
                "common_python_tasks.project.get_project_version",
                return_value="1.2.3",
            ),
            patch(
                "common_python_tasks.git.infer_bump_component_from_git_cliff",
                return_value=ReleaseComponent.MINOR,
            ),
        ):
            result = self._call("auto")
            assert result.version == "1.3.0"
            assert result.component == "minor"

    def test_auto_uses_git_cliff_inference_for_pre_production(self):
        from common_python_tasks.git import ReleaseComponent

        with (
            patch(
                "common_python_tasks.git.infer_bump_component_from_git_cliff",
                return_value=ReleaseComponent.MAJOR,
            ),
        ):
            result = self._call("auto", current_version="0.3.1")
            assert result.version == "1.0.0"
            assert result.component == "major"

    def test_accepts_enum_inputs(self):
        from common_python_tasks.git import ReleaseComponent, ReleaseStage

        result = self._call(ReleaseComponent.PATCH, stage=ReleaseStage.BETA)
        assert result.version == "1.2.4b1"

    def test_invalid_component_exits(self):
        with pytest.raises(SystemExit):
            self._call("invalid")

    def test_invalid_stage_exits(self):
        with pytest.raises(SystemExit):
            self._call("patch", stage="gamma")


class TestHasTagsLaterInHistory:
    def test_no_tags_exist(self):
        from common_python_tasks.git import has_tags_later_in_history

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
        from common_python_tasks.git import has_tags_later_in_history

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
        from common_python_tasks.git import has_tags_later_in_history

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
        from common_python_tasks.git import has_tags_later_in_history

        with patch("common_python_tasks.utils.run_command") as mock:

            def side_effect(command, *args, **kwargs):
                result = MagicMock()
                if command == ["git", "tag"]:
                    result.returncode = 128
                    result.stdout = ""
                return result

            mock.side_effect = side_effect

            assert not has_tags_later_in_history()


class TestGetDirtyFiles:
    def test_returns_empty_list_when_no_dirty_files(self):
        from common_python_tasks.git import get_dirty_files

        with patch("common_python_tasks.utils.run_command") as mock_run:
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            result = get_dirty_files()
            assert result == []

    def test_parses_porcelain_output(self):
        from pathlib import Path

        from common_python_tasks.git import get_dirty_files

        porcelain_output = " M src/file.py\n?? new_file.txt\nA  added.py\n"
        with patch("common_python_tasks.utils.run_command") as mock_run:
            mock_run.return_value = MagicMock(stdout=porcelain_output, returncode=0)
            result = get_dirty_files()
            assert result == [
                Path("src/file.py"),
                Path("new_file.txt"),
                Path("added.py"),
            ]

    def test_respects_ignore_list(self):
        from pathlib import Path

        from common_python_tasks.git import get_dirty_files

        porcelain_output = " M src/file.py\n?? new_file.txt\n"
        with patch("common_python_tasks.utils.run_command") as mock_run:
            mock_run.return_value = MagicMock(stdout=porcelain_output, returncode=0)
            result = get_dirty_files(ignore=[Path("new_file.txt")])
            assert result == [Path("src/file.py")]


class TestGetVersion:
    def test_returns_version_with_dirty_suffix(self):
        from common_python_tasks.git import get_version

        with (
            patch("common_python_tasks.git.get_dirty_files") as mock_dirty,
            patch("common_python_tasks.git.Version") as mock_version,
        ):
            mock_dirty.return_value = ["/some/file.py"]
            mock_instance = MagicMock()
            mock_instance.serialize.return_value = "1.2.3+dirty"
            mock_version.from_git.return_value = mock_instance

            result = get_version()
            assert result == "1.2.3+dirty"
            mock_instance.serialize.assert_called_once()


class TestGetImageTag:
    def test_normalizes_docker_unsafe_characters(self):
        from common_python_tasks.git import get_image_tag

        with patch("common_python_tasks.git.get_version") as mock_version:
            mock_version.return_value = "1.2.3.post0.dev123+abc"
            result = get_image_tag()
            assert result == "1.2.3-post0-dev123-abc"

    def test_respects_ignore_list(self):
        from pathlib import Path

        from common_python_tasks.git import get_image_tag

        with patch("common_python_tasks.git.get_version") as mock_version:
            mock_version.return_value = "2.0.0+dirty"
            result = get_image_tag(ignore=[Path("CHANGELOG.md")])
            assert result == "2.0.0-dirty"

    def test_get_version_falls_back_when_git_unavailable(self):
        from common_python_tasks.git import get_image_tag, get_version

        with patch("common_python_tasks.git.shutil.which", return_value=None):
            assert get_version() == "0.0.0"
            assert get_image_tag() == "0.0.0"


def test_get_default_branch_uses_origin_head():
    from common_python_tasks.git import get_default_branch

    with patch(
        "common_python_tasks.utils.run_command",
        return_value=MagicMock(stdout="refs/remotes/origin/trunk\n", returncode=0),
    ):
        assert get_default_branch() == "trunk"


def test_get_current_branch_rejects_detached_head():
    from common_python_tasks.git import get_current_branch

    with (
        patch(
            "common_python_tasks.utils.run_command",
            return_value=MagicMock(stdout="\n", returncode=0),
        ),
        pytest.raises(SystemExit),
    ):
        get_current_branch()
