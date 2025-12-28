import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest


class TestDockerignoreHandling:
    """Tests for .dockerignore file handling during image builds."""

    def test_uses_builtin_dockerignore_when_missing(
        self,
        temp_project_dir: Path,
        mock_run_command: MagicMock,
        mock_load_data_file: MagicMock,
        mock_get_image_tag: MagicMock,
        mock_get_authors: MagicMock,
        mock_get_package_name: MagicMock,
    ):
        """Test that built-in .dockerignore is used when none exists."""
        from common_python_tasks.tasks import _build_image

        dockerignore_path = temp_project_dir / ".dockerignore"
        assert not dockerignore_path.exists()

        _build_image(
            containerfile_path=None,
            containerfile_text="FROM python:3.11\n",
            context_path=temp_project_dir,
        )

        mock_load_data_file.assert_any_call(".dockerignore")

        assert not dockerignore_path.exists()

    def test_preserves_existing_dockerignore(
        self,
        temp_project_dir: Path,
        mock_run_command: MagicMock,
        mock_get_image_tag: MagicMock,
        mock_get_authors: MagicMock,
        mock_get_package_name: MagicMock,
    ):
        """Test that existing .dockerignore is not modified."""
        from common_python_tasks.tasks import _build_image

        dockerignore_path = temp_project_dir / ".dockerignore"
        original_content = "# Custom dockerignore\n*.log\n"
        dockerignore_path.write_text(original_content)

        _build_image(
            containerfile_path=None,
            containerfile_text="FROM python:3.11\n",
            context_path=temp_project_dir,
        )

        assert dockerignore_path.exists()
        assert dockerignore_path.read_text() == original_content

    def test_temporary_dockerignore_created_and_removed(
        self,
        temp_project_dir: Path,
        mock_run_command: MagicMock,
        mock_load_data_file: MagicMock,
        mock_get_image_tag: MagicMock,
        mock_get_authors: MagicMock,
        mock_get_package_name: MagicMock,
    ):
        """Test that temporary .dockerignore is created and removed."""
        from common_python_tasks.tasks import _build_image

        dockerignore_path = temp_project_dir / ".dockerignore"
        assert not dockerignore_path.exists()

        dockerignore_existed_during_build = False

        original_run_command = mock_run_command.side_effect

        def tracking_side_effect(command, *args, **kwargs):
            nonlocal dockerignore_existed_during_build
            if "docker" in command and "build" in command:
                dockerignore_existed_during_build = dockerignore_path.exists()
            return original_run_command(command, *args, **kwargs)

        mock_run_command.side_effect = tracking_side_effect

        _build_image(
            containerfile_path=None,
            containerfile_text="FROM python:3.11\n",
            context_path=temp_project_dir,
        )

        assert dockerignore_existed_during_build

        assert not dockerignore_path.exists()

    def test_temporary_dockerignore_cleanup_on_error(
        self,
        temp_project_dir: Path,
        mock_run_command: MagicMock,
        mock_load_data_file: MagicMock,
        mock_get_image_tag: MagicMock,
        mock_get_authors: MagicMock,
        mock_get_package_name: MagicMock,
    ):
        """Test that temporary .dockerignore is cleaned up even on error."""
        from common_python_tasks.tasks import _build_image

        dockerignore_path = temp_project_dir / ".dockerignore"

        def failing_side_effect(command, *args, **kwargs):
            result = MagicMock(spec=subprocess.CompletedProcess)
            if "docker" in command and "build" in command:
                result.returncode = 1
                result.stdout = ""
                result.stderr = "Build failed"
                import sys

                sys.exit(1)
            result.returncode = 0
            if "git" in command and "status" in command and "--porcelain" in command:
                result.stdout = ""
            elif "git" in command and "rev-parse" in command:
                result.stdout = "abc1234"
            elif "poetry" in command and "--version" in command:
                result.stdout = "Poetry (version 1.8.0)"
            else:
                result.stdout = ""
            return result

        mock_run_command.side_effect = failing_side_effect

        with pytest.raises(SystemExit):
            _build_image(
                containerfile_path=None,
                containerfile_text="FROM python:3.11\n",
                context_path=temp_project_dir,
            )

        assert not dockerignore_path.exists()

    def test_dockerignore_content_from_builtin(
        self,
        temp_project_dir: Path,
        mock_run_command: MagicMock,
        mock_load_data_file: MagicMock,
        mock_get_image_tag: MagicMock,
        mock_get_authors: MagicMock,
        mock_get_package_name: MagicMock,
    ):
        """Test that the correct content is written from built-in .dockerignore."""
        from common_python_tasks.tasks import _build_image

        dockerignore_path = temp_project_dir / ".dockerignore"
        expected_content = "*\n!dist/*.whl\n!pyproject.toml\n"

        actual_content = None
        original_run_command = mock_run_command.side_effect

        def tracking_side_effect(command, *args, **kwargs):
            nonlocal actual_content
            if "docker" in command and "build" in command:
                if dockerignore_path.exists():
                    actual_content = dockerignore_path.read_text()
            return original_run_command(command, *args, **kwargs)

        mock_run_command.side_effect = tracking_side_effect

        _build_image(
            containerfile_path=None,
            containerfile_text="FROM python:3.11\n",
            context_path=temp_project_dir,
        )

        assert actual_content == expected_content


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

        build_command = None
        original_side_effect = mock_run_command.side_effect

        def tracking_side_effect(command, *args, **kwargs):
            nonlocal build_command
            result = original_side_effect(command, *args, **kwargs)
            if command == ["git", "tag"]:
                result.stdout = "v1.0.0"
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

        build_command = None
        original_side_effect = mock_run_command.side_effect

        def tracking_side_effect(command, *args, **kwargs):
            nonlocal build_command
            result = original_side_effect(command, *args, **kwargs)
            if command == ["git", "tag"]:
                result.stdout = "v1.0.0\nv2.0.0"
            elif command[:3] == ["git", "merge-base", "--is-ancestor"]:
                if command[-1] == "v2.0.0":
                    result.returncode = 1
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

        assert build_command is not None
        tag_args = [
            build_command[i + 1]
            for i, arg in enumerate(build_command)
            if arg == "-t" and i + 1 < len(build_command)
        ]
        assert not any("latest" in tag for tag in tag_args)
