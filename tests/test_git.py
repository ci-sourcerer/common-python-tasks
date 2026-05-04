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
            "common_python_tasks.project.get_project_version_from_poetry",
            return_value="1.3.2",
        ),
    ):
        from common_python_tasks.git import infer_bump_component_from_git_cliff

        assert infer_bump_component_from_git_cliff() == "major"


class TestComputeNextReleaseVersion:
    def _call(self, component, stage=None, current_version="1.2.3"):
        with patch(
            "common_python_tasks.project.get_project_version_from_poetry",
            return_value=current_version,
        ):
            from common_python_tasks.git import compute_next_release_version

            return compute_next_release_version(component, stage)

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
        with (
            patch(
                "common_python_tasks.project.get_project_version_from_poetry",
                return_value="1.2.3",
            ),
            patch(
                "common_python_tasks.git.infer_bump_component_from_git_cliff",
                return_value="minor",
            ),
        ):
            from common_python_tasks.git import compute_next_release_version

            result = compute_next_release_version("auto", None)
            assert result.version == "1.3.0"
            assert result.component == "minor"

    def test_auto_forces_patch_for_pre_production(self):
        with (
            patch(
                "common_python_tasks.project.get_project_version_from_poetry",
                return_value="0.3.1",
            ),
            patch(
                "common_python_tasks.git.infer_bump_component_from_git_cliff",
                return_value="major",
            ),
        ):
            from common_python_tasks.git import compute_next_release_version

            result = compute_next_release_version("auto", None)
            assert result.version == "0.3.2"
            assert result.component == "patch"

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
