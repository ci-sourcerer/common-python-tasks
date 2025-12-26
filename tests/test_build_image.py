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

        # Ensure no .dockerignore exists
        dockerignore_path = temp_project_dir / ".dockerignore"
        assert not dockerignore_path.exists()

        # Build image
        _build_image(
            containerfile_path=None,
            containerfile_text="FROM python:3.11\n",
            context_path=temp_project_dir,
        )

        # Verify .dockerignore was loaded
        mock_load_data_file.assert_any_call(".dockerignore")

        # Verify .dockerignore was cleaned up after build
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

        # Create existing .dockerignore
        dockerignore_path = temp_project_dir / ".dockerignore"
        original_content = "# Custom dockerignore\n*.log\n"
        dockerignore_path.write_text(original_content)

        # Build image
        _build_image(
            containerfile_path=None,
            containerfile_text="FROM python:3.11\n",
            context_path=temp_project_dir,
        )

        # Verify existing .dockerignore is preserved with original content
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

        # Track .dockerignore state during build
        dockerignore_existed_during_build = False

        original_run_command = mock_run_command.side_effect

        def tracking_side_effect(command, *args, **kwargs):
            nonlocal dockerignore_existed_during_build
            # Check if .dockerignore exists when docker build is called
            if "docker" in command and "build" in command:
                dockerignore_existed_during_build = dockerignore_path.exists()
            return original_run_command(command, *args, **kwargs)

        mock_run_command.side_effect = tracking_side_effect

        _build_image(
            containerfile_path=None,
            containerfile_text="FROM python:3.11\n",
            context_path=temp_project_dir,
        )

        # Verify .dockerignore existed during build
        assert dockerignore_existed_during_build

        # Verify .dockerignore was cleaned up after build
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

        # Make docker build fail
        def failing_side_effect(command, *args, **kwargs):
            result = MagicMock(spec=subprocess.CompletedProcess)
            if "docker" in command and "build" in command:
                result.returncode = 1
                result.stdout = ""
                result.stderr = "Build failed"
                # Raise SystemExit as _run_command does on failure
                import sys

                sys.exit(1)
            result.returncode = 0
            # Provide proper return values for non-docker commands
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

        # Build should fail
        with pytest.raises(SystemExit):
            _build_image(
                containerfile_path=None,
                containerfile_text="FROM python:3.11\n",
                context_path=temp_project_dir,
            )

        # Verify .dockerignore was cleaned up despite error
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

        # Track content during build
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

        # Verify content matches built-in .dockerignore
        assert actual_content == expected_content
