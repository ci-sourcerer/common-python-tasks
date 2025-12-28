"""Shared pytest fixtures and helpers for all tests."""

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from pytest import MonkeyPatch


@pytest.fixture
def mock_run_command():
    """Mock _run_command with standard return values for common git/poetry commands."""
    with patch("common_python_tasks.tasks._run_command") as mock:

        def side_effect(command, *args, **kwargs):
            result = MagicMock(spec=subprocess.CompletedProcess)
            result.returncode = 0
            if "git" in command and "status" in command and "--porcelain" in command:
                result.stdout = ""
            elif "git" in command and "rev-parse" in command:
                result.stdout = "abc1234"
            elif "poetry" in command and "--version" in command:
                result.stdout = "Poetry (version 1.8.0)"
            elif "docker" in command:
                result.stdout = ""
            else:
                result.stdout = ""
            return result

        mock.side_effect = side_effect
        yield mock


@pytest.fixture
def mock_load_data_file():
    """Mock _load_data_file to return test data."""
    with patch("common_python_tasks.tasks._load_data_file") as mock:

        def side_effect(filename):
            if filename == "Containerfile":
                return ("/fake/path/Containerfile", "FROM python:3.11\n")
            elif filename == ".dockerignore":
                return (
                    "/fake/path/.dockerignore",
                    "*\n!dist/*.whl\n!pyproject.toml\n",
                )
            return ("/fake/path/" + filename, "")

        mock.side_effect = side_effect
        yield mock


@pytest.fixture
def mock_get_image_tag():
    """Mock _get_image_tag to return a fixed tag."""
    with patch("common_python_tasks.tasks._get_image_tag") as mock:
        mock.return_value = "1.0.0"
        yield mock


@pytest.fixture
def mock_get_authors():
    """Mock _get_authors to return test authors."""
    with patch("common_python_tasks.tasks._get_authors") as mock:
        mock.return_value = [("Test Author", "test@example.com")]
        yield mock


@pytest.fixture
def mock_get_package_name():
    """Mock _get_package_name to return a test package name."""
    with patch("common_python_tasks.tasks._get_package_name") as mock:
        mock.return_value = "test-package"
        yield mock


@pytest.fixture
def temp_project_dir(tmp_path: Path, monkeypatch: "MonkeyPatch"):
    """Create a temporary project directory with minimal pyproject.toml."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    pyproject_content = """
[project]
name = "test-package"
version = "0.1.0"
authors = [
    {name = "Test Author", email = "test@example.com"}
]
"""
    (project_dir / "pyproject.toml").write_text(pyproject_content)

    monkeypatch.chdir(project_dir)

    return project_dir
