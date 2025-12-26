"""Tests for _has_tags_later_in_history helper function."""

import subprocess
from unittest.mock import MagicMock, patch


class TestHasTagsLaterInHistory:
    """Tests for checking if there are tags later in git history."""

    def test_no_tags_exist(self):
        """Test when no tags exist in the repository."""
        from common_python_tasks.tasks import _has_tags_later_in_history

        with patch("common_python_tasks.tasks._run_command") as mock:

            def side_effect(command, *args, **kwargs):
                result = MagicMock(spec=subprocess.CompletedProcess)
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
                result = MagicMock(spec=subprocess.CompletedProcess)
                if command == ["git", "tag"]:
                    result.returncode = 0
                    result.stdout = "v1.0.0\nv1.1.0\nv1.2.0"
                elif command[:3] == ["git", "merge-base", "--is-ancestor"]:
                    # All tags are ancestors of HEAD
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
                result = MagicMock(spec=subprocess.CompletedProcess)
                if command == ["git", "tag"]:
                    result.returncode = 0
                    result.stdout = "v1.0.0\nv1.1.0\nv2.0.0"
                elif command[:3] == ["git", "merge-base", "--is-ancestor"]:
                    # First two tags are ancestors, third is not
                    call_count += 1
                    if call_count <= 2:
                        result.returncode = 0  # v1.0.0 and v1.1.0 are ancestors
                    else:
                        result.returncode = 1  # v2.0.0 is NOT an ancestor
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
                result = MagicMock(spec=subprocess.CompletedProcess)
                if command == ["git", "tag"]:
                    result.returncode = 128
                    result.stdout = ""
                return result

            mock.side_effect = side_effect

            assert not _has_tags_later_in_history()


class TestBuildImageLatestTag:
    """Tests for latest tag behavior in build_image."""

    def test_latest_tag_when_no_future_tags(
        self,
        temp_project_dir,
        mock_run_command,
        mock_load_data_file,
        mock_get_image_tag,
        mock_get_authors,
        mock_get_package_name,
    ):
        """Test that 'latest' tag is used when no tags are later in history."""
        from common_python_tasks.tasks import _build_image

        # Track the docker build command
        build_command = None
        original_side_effect = mock_run_command.side_effect

        def tracking_side_effect(command, *args, **kwargs):
            nonlocal build_command
            result = original_side_effect(command, *args, **kwargs)
            # Intercept git tag command to return tags
            if command == ["git", "tag"]:
                result.stdout = "v1.0.0"
            # Make all tags ancestors of HEAD
            elif command[:3] == ["git", "merge-base", "--is-ancestor"]:
                result.returncode = 0
            elif "docker" in command and "build" in command:
                build_command = command
            return result

        mock_run_command.side_effect = tracking_side_effect

        _build_image(
            containerfile_path=None,
            containerfile_text="FROM python:3.11\n",
            context_path=temp_project_dir,
        )

        # Verify 'latest' tag was included
        assert build_command is not None
        assert any("latest" in str(arg) for arg in build_command)

    def test_no_latest_tag_when_future_tags_exist(
        self,
        temp_project_dir,
        mock_run_command,
        mock_load_data_file,
        mock_get_image_tag,
        mock_get_authors,
        mock_get_package_name,
    ):
        """Test that 'latest' tag is NOT used when tags are later in history."""
        from common_python_tasks.tasks import _build_image

        # Track the docker build command
        build_command = None
        original_side_effect = mock_run_command.side_effect

        def tracking_side_effect(command, *args, **kwargs):
            nonlocal build_command
            result = original_side_effect(command, *args, **kwargs)
            # Intercept git tag command to return tags
            if command == ["git", "tag"]:
                result.stdout = "v1.0.0\nv2.0.0"
            # Make the second tag NOT an ancestor of HEAD
            elif command[:3] == ["git", "merge-base", "--is-ancestor"]:
                if command[-1] == "v2.0.0":
                    result.returncode = 1  # v2.0.0 is later in history
                else:
                    result.returncode = 0
            elif "docker" in command and "build" in command:
                build_command = command
            return result

        mock_run_command.side_effect = tracking_side_effect

        _build_image(
            containerfile_path=None,
            containerfile_text="FROM python:3.11\n",
            context_path=temp_project_dir,
        )

        # Verify 'latest' tag was NOT included
        assert build_command is not None
        # Check that 'latest' does not appear in any of the tag arguments
        tag_args = [
            build_command[i + 1]
            for i, arg in enumerate(build_command)
            if arg == "-t" and i + 1 < len(build_command)
        ]
        assert not any("latest" in tag for tag in tag_args)
