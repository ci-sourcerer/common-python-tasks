import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if TYPE_CHECKING:
    from pytest import MonkeyPatch


@pytest.fixture(scope="session", autouse=True)
def _set_test_environment_variables():
    """Set environment variables required for tests to pass.

    These variables are set in [tool.poe.env] and need to be available
    when running pytest directly.
    """
    os.environ.setdefault("RELEASE_UPDATE_CHANGELOG", "1")
    os.environ.setdefault(
        "RELEASE_PRE_SCRIPT",
        "RELEASE_SCRIPT_PHASE=pre python -m scripts.release_script",
    )
    os.environ.setdefault(
        "RELEASE_POST_SCRIPT",
        "RELEASE_SCRIPT_PHASE=post python -m scripts.release_script",
    )
    os.environ.setdefault("COMMON_PYTHON_TASKS_PACKAGE_MANAGER", "poetry")


@pytest.fixture
def mock_run_command():
    """Mock _run_command with standard return values for common git/poetry commands."""
    mock = MagicMock()

    with patch("common_python_tasks.utils.run_command", new=mock):

        def side_effect(command, *args, **kwargs):
            result = MagicMock(spec=subprocess.CompletedProcess)
            result.returncode = 0
            if (
                "git" in command
                and "rev-parse" in command
                and "--is-inside-work-tree" in command
            ):
                result.stdout = "true"
            elif "git" in command and "status" in command and "--porcelain" in command:
                result.stdout = ""
            elif "git" in command and "rev-parse" in command:
                result.stdout = "abc1234"
            elif "poetry" in command and "--version" in command:
                result.stdout = "Poetry (version 1.8.0)"
            elif command[:2] == ["uv", "--version"]:
                result.stdout = "uv 0.8.0"
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
    mock = MagicMock()
    version_mock = MagicMock()

    with (
        patch("common_python_tasks.utils.load_data_file", new=mock),
        patch(
            "common_python_tasks.project.get_installed_requirement_version",
            new=version_mock,
        ),
    ):
        version_mock.side_effect = lambda name: {
            "poetry-dynamic-versioning[plugin]": "0.17.0",
            "poetry-plugin-export": "1.5.0",
        }.get(name)

        def side_effect(filename, type_identifier="generic", fatal_on_missing=True):
            # normalize inputs for both call styles (old: single `filename`, new: `file, type_identifier`)
            key = filename
            if type_identifier == "dockerfile_extensions":
                # new top-level call style: filename will be like "jq/Dockerfile"
                key = f"dockerfile_extensions/{filename}"

            if key == "Dockerfile" or key == "Dockerfile.j2":
                return ("/fake/path/Dockerfile.j2", "FROM python:3.11\n")
            elif key == "Dockerfile.deps.j2":
                return (
                    "/fake/path/Dockerfile.deps.j2",
                    "FROM python:3.11 AS deps\nRUN mkdir -p /tmp/deps\n{{ DEPS_CONTENT }}\n",
                )
            elif key == "dockerfile_extensions/template_bundle/Dockerfile":
                return (
                    "/fake/path/Dockerfile.template_bundle",
                    "# template bundle used by tests\nUSER root\nARG CONTAINER_APT_PACKAGES\nRUN apt-get update && apt-get install -y --no-install-recommends ${CONTAINER_APT_PACKAGES} && rm -rf /var/lib/apt/lists/*\nUSER py\n",
                )
            elif key == ".dockerignore":
                return (
                    "/fake/path/.dockerignore",
                    "*\n!dist/*.whl\n!pyproject.toml\n",
                )
            if not fatal_on_missing:
                return None
            return ("/fake/path/" + key, "")

        mock.side_effect = side_effect
        yield mock


@pytest.fixture
def mock_get_image_tag():
    """Mock get_image_tag and get_version to return fixed values."""
    image_tag_mock = MagicMock(return_value="1.0.0")
    version_mock = MagicMock(return_value="1.0.0")
    with (
        patch("common_python_tasks.git.get_image_tag", new=image_tag_mock),
        patch("common_python_tasks.git.get_version", new=version_mock),
    ):
        yield image_tag_mock


@pytest.fixture
def mock_find_spec():
    """Mock importlib.util.find_spec for package availability testing."""
    with patch("importlib.util.find_spec") as mock:
        yield mock


@pytest.fixture
def mock_get_authors():
    """Mock _get_authors to return test authors."""
    mock = MagicMock()
    with patch("common_python_tasks.project.get_authors", new=mock):
        mock.return_value = [("Test Author", "test@example.com")]
        yield mock


@pytest.fixture
def mock_get_package_name():
    """Mock _get_package_name to return a test package name."""
    mock = MagicMock()
    with patch("common_python_tasks.utils.get_package_name", new=mock):
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

    from common_python_tasks.project import (
        has_debug_dependency_group,
        is_task_tag_included,
        read_pyproject_toml,
    )

    has_debug_dependency_group.cache_clear()
    is_task_tag_included.cache_clear()
    read_pyproject_toml.cache_clear()

    return project_dir
