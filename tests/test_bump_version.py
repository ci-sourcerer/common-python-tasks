import subprocess
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def tag_calls():
    """Collect git tag arguments issued by bump_version."""
    return []


@pytest.fixture
def mock_run_command_no_tags(tag_calls, mock_run_command):
    """Mock _run_command to simulate a repo with no tags and clean status."""
    del mock_run_command  # Disable the standard mock; we'll replace it
    with patch("common_python_tasks.tasks._run_command") as mock:

        def side_effect(command, *args, **kwargs):
            result = MagicMock(spec=subprocess.CompletedProcess)
            # Clean working tree
            if command[:3] == ["git", "status", "--porcelain"]:
                result.returncode = 0
                result.stdout = ""
            # No tags yet
            elif command[:4] == ["git", "describe", "--tags", "--abbrev=0"]:
                result.returncode = 128
                result.stdout = ""
            # Capture created tag
            elif len(command) >= 3 and command[0] == "git" and command[1] == "tag":
                result.returncode = 0
                # last arg is the tag name (e.g., 'v1.0.0')
                tag_calls.append(command[-1])
                result.stdout = ""
            else:
                result.returncode = 0
                result.stdout = ""
            return result

        mock.side_effect = side_effect
        yield mock


def test_bump_major_no_tags(mock_run_command_no_tags, tag_calls):
    from common_python_tasks.tasks import bump_version

    bump_version("major")
    assert tag_calls[-1] == "v1.0.0"


def test_bump_minor_no_tags(mock_run_command_no_tags, tag_calls):
    from common_python_tasks.tasks import bump_version

    bump_version("minor")
    assert tag_calls[-1] == "v0.1.0"


def test_bump_patch_no_tags(mock_run_command_no_tags, tag_calls):
    from common_python_tasks.tasks import bump_version

    bump_version("patch")
    assert tag_calls[-1] == "v0.0.1"


def test_bump_patch_alpha_no_tags(mock_run_command_no_tags, tag_calls):
    from common_python_tasks.tasks import bump_version

    bump_version("patch", stage="alpha")
    # PEP 440 alpha suffix should be 'a1'
    assert tag_calls[-1] == "v0.0.1a1"
