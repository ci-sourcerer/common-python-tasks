from unittest.mock import MagicMock, patch


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
