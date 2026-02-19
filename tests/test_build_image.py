import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest


class TestParseContainerExtensions:
    """Tests for _parse_container_extensions parameter parsing."""

    def test_plain_bundle_name(self, monkeypatch):
        from common_python_tasks.tasks import _parse_container_extensions

        monkeypatch.delenv("CONTAINER_EXTENSION_FILES", raising=False)
        monkeypatch.setenv("CONTAINER_EXTENSIONS", "some_ext")

        result = _parse_container_extensions()
        assert len(result) == 1
        assert result[0]["id"] == "some_ext"
        assert result[0]["bundle_name"] == "some_ext"
        assert result[0]["args"] is None

    def test_parameterised_bundle(self, monkeypatch):
        from common_python_tasks.tasks import _parse_container_extensions

        monkeypatch.delenv("CONTAINER_EXTENSION_FILES", raising=False)
        monkeypatch.setenv("CONTAINER_EXTENSIONS", "some_ext=jq curl")

        result = _parse_container_extensions()
        assert len(result) == 1
        assert result[0]["id"] == "some_ext"
        assert result[0]["bundle_name"] == "some_ext"
        assert result[0]["args"] == "jq curl"

    def test_mixed_parameterised_and_plain(self, monkeypatch):
        from common_python_tasks.tasks import _parse_container_extensions

        monkeypatch.delenv("CONTAINER_EXTENSION_FILES", raising=False)
        monkeypatch.setenv("CONTAINER_EXTENSIONS", "some_ext=jq curl wget:plain_ext")

        result = _parse_container_extensions()
        assert len(result) == 2
        assert result[0]["id"] == "some_ext"
        assert result[0]["args"] == "jq curl wget"
        assert result[1]["id"] == "plain_ext"
        assert result[1]["args"] is None

    def test_empty_args_treated_as_empty_string(self, monkeypatch):
        from common_python_tasks.tasks import _parse_container_extensions

        monkeypatch.delenv("CONTAINER_EXTENSION_FILES", raising=False)
        monkeypatch.setenv("CONTAINER_EXTENSIONS", "some_ext=")

        result = _parse_container_extensions()
        assert len(result) == 1
        assert result[0]["args"] == ""


class TestResolveExtensionContent:
    """Tests for _resolve_extension_content (no template substitution).

    Argument passing is now handled via Docker build-args; this function only
    returns the fragment content unchanged.
    """

    def test_template_contains_build_arg_variable(self, mock_load_data_file):
        from common_python_tasks.tasks import _resolve_extension_content

        desc = {
            "id": "template_bundle",
            "source": "bundle",
            "path": None,
            "bundle_name": "template_bundle",
            "args": "jq curl",
        }
        content = _resolve_extension_content(desc)
        assert "APT_PACKAGES" in content
        assert "jq curl" not in content

    def test_missing_args_do_not_affect_content(self, mock_load_data_file):
        from common_python_tasks.tasks import _resolve_extension_content

        desc = {
            "id": "template_bundle",
            "source": "bundle",
            "path": None,
            "bundle_name": "template_bundle",
            "args": None,
        }
        # Should simply return the template content (argument application
        # happens at build time)
        content = _resolve_extension_content(desc)
        assert "APT_PACKAGES" in content

    def test_file_extension_without_placeholder_and_no_args(self, tmp_path):
        from common_python_tasks.tasks import _resolve_extension_content

        ext_file = tmp_path / "Containerfile.custom"
        ext_file.write_text("RUN echo hello\n")

        desc = {
            "id": "custom",
            "source": "file",
            "path": str(ext_file),
            "bundle_name": None,
            "args": None,
        }
        content = _resolve_extension_content(desc)
        assert content == "RUN echo hello\n"


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


def test_build_with_multiple_extensions(
    temp_project_dir,
    mock_run_command,
    mock_load_data_file,
    mock_get_image_tag,
    mock_get_authors,
    mock_get_package_name,
    monkeypatch,
):
    """Building with multiple extension Containerfiles should build base + extensions.

    Use local `Containerfile.<name>` fixtures (not bundled test fragments).
    """
    from common_python_tasks.tasks import build_image

    # create two local extension Containerfile fragments
    ext1 = temp_project_dir / "Containerfile.ext1"
    ext1.write_text("# ext1\nRUN echo ext1\n")
    ext2 = temp_project_dir / "Containerfile.ext2"
    ext2.write_text("# ext2\nRUN echo ext2\n")

    monkeypatch.setenv(
        "CONTAINER_EXTENSION_FILES", "Containerfile.ext1:Containerfile.ext2"
    )
    # Ensure any bundled CONTAINER_EXTENSIONS in the outer environment do not affect this test
    monkeypatch.delenv("CONTAINER_EXTENSIONS", raising=False)

    build_calls: list[list[str]] = []
    original = mock_run_command.side_effect

    def tracking(command, *args, **kwargs):
        if "docker" in command and "build" in command:
            build_calls.append(command)
        return original(command, *args, **kwargs)

    mock_run_command.side_effect = tracking

    build_image()

    # Expect 2 docker build invocations: base + stacked extensions
    assert len(build_calls) == 2


def test_prune_removes_base_images_when_enabled(
    temp_project_dir,
    mock_run_command,
    mock_load_data_file,
    mock_get_image_tag,
    mock_get_authors,
    mock_get_package_name,
    monkeypatch,
):
    """When CONTAINER_PRUNE is truthy, base image tags should be removed after builds.

    Use a local extension file (not bundled test fragment).
    """
    from common_python_tasks.tasks import build_image

    # create a local extension fragment to exercise extension build path
    ext = temp_project_dir / "Containerfile.ext1"
    ext.write_text("# ext1\nRUN echo ext1\n")

    monkeypatch.setenv("CONTAINER_EXTENSION_FILES", "Containerfile.ext1")
    monkeypatch.setenv("CONTAINER_PRUNE_KEEP", "0")

    calls: list[list[str]] = []

    def tracking(command, *args, **kwargs):
        # Provide a fake `docker image ls` output (newest first)
        if len(command) >= 3 and command[:3] == ["docker", "image", "ls"]:
            result = original_side_effect(command, *args, **kwargs)
            # newest-first list for repository 'docker.io/test-package'
            result.stdout = (
                "docker.io/test-package:latest\n"
                "docker.io/test-package:1.0.0\n"
                "docker.io/test-package:abc1234\n"
                "docker.io/test-package:old-tag\n"
            )
            return result

        calls.append(command)
        return original_side_effect(command, *args, **kwargs)

    original_side_effect = mock_run_command.side_effect
    mock_run_command.side_effect = tracking

    build_image()

    # Ensure docker rmi was called for the older, non-protected tag only
    rmi_calls = [c for c in calls if c[:2] == ["docker", "rmi"]]

    assert any("old-tag" in str(call) for call in rmi_calls)
    assert not any("1.0.0" in str(call) for call in rmi_calls)
    assert not any("abc1234" in str(call) for call in rmi_calls)


def test_no_prune_on_extension_failure(
    temp_project_dir,
    mock_run_command,
    mock_load_data_file,
    mock_get_image_tag,
    mock_get_authors,
    mock_get_package_name,
    monkeypatch,
):
    """If an extension build fails, pruning should not run and base images remain.

    Use local extension Containerfile fixtures instead of bundled test fragments.
    """
    from common_python_tasks.tasks import build_image

    # local extension fixtures
    ext1 = temp_project_dir / "Containerfile.ext1"
    ext1.write_text("# ext1\nRUN echo ext1\n")
    ext2 = temp_project_dir / "Containerfile.ext2"
    ext2.write_text("# ext2\nRUN echo ext2\n")

    monkeypatch.setenv(
        "CONTAINER_EXTENSION_FILES", "Containerfile.ext1:Containerfile.ext2"
    )
    monkeypatch.setenv("CONTAINER_PRUNE_KEEP", "0")

    call_count = 0
    original = mock_run_command.side_effect

    def failing_side_effect(command, *args, **kwargs):
        nonlocal call_count
        if "docker" in command and "build" in command:
            call_count += 1
            # Fail the second build (first is base, second is first extension)
            if call_count == 2:
                import sys

                sys.exit(1)
        return original(command, *args, **kwargs)

    mock_run_command.side_effect = failing_side_effect

    with pytest.raises(SystemExit):
        build_image()

    # Ensure no docker rmi calls were made
    calls = [c for c in mock_run_command.call_args_list]
    assert not any("rmi" in str(c) for c in calls)


def test_extension_template_support(
    temp_project_dir,
    mock_run_command,
    mock_load_data_file,
    mock_get_image_tag,
    mock_get_authors,
    mock_get_package_name,
    monkeypatch,
):
    """CONTAINER_EXTENSIONS should load bundled Containerfile templates.

    Verify APT_PACKAGES can be provided via CONTAINER_BUILD_ARGS and is passed to the build.
    """
    from common_python_tasks.tasks import build_image

    monkeypatch.setenv("CONTAINER_BUILD_ARGS", "APT_PACKAGES=jq")

    build_calls: list[list[str]] = []
    original = mock_run_command.side_effect

    def tracking(command, *args, **kwargs):
        if "docker" in command and "build" in command:
            build_calls.append(command)
        return original(command, *args, **kwargs)

    mock_run_command.side_effect = tracking

    build_image()

    # Only the base build should run (no extra extension image)
    assert len(build_calls) == 1

    # Ensure build-arg for APT_PACKAGES was passed to the base build
    base_build_cmd = build_calls[0]
    assert any("APT_PACKAGES=jq" in str(a) for a in base_build_cmd)


def test_build_arg_with_multiple_packages(
    temp_project_dir,
    mock_run_command,
    mock_load_data_file,
    mock_get_image_tag,
    mock_get_authors,
    mock_get_package_name,
    monkeypatch,
):
    from common_python_tasks.tasks import build_image

    monkeypatch.setenv("CONTAINER_BUILD_ARGS", "APT_PACKAGES=jq curl")

    build_calls: list[list[str]] = []
    original = mock_run_command.side_effect

    def tracking(command, *args, **kwargs):
        if "docker" in command and "build" in command:
            build_calls.append(command)
        return original(command, *args, **kwargs)

    mock_run_command.side_effect = tracking

    build_image()

    # Verify base build received the multi-package build-arg
    assert len(build_calls) == 1
    base_build_cmd = build_calls[0]
    assert any("APT_PACKAGES=jq curl" in str(a) for a in base_build_cmd)


def test_build_image_accepts_build_args_param(
    temp_project_dir,
    mock_run_command,
    mock_load_data_file,
    mock_get_image_tag,
    mock_get_authors,
    mock_get_package_name,
):
    # Ensure env not set so CLI param is used
    import os

    from common_python_tasks.tasks import build_image

    os.environ.pop("CONTAINER_BUILD_ARGS", None)

    build_calls: list[list[str]] = []
    original = mock_run_command.side_effect

    def tracking(command, *args, **kwargs):
        if "docker" in command and "build" in command:
            build_calls.append(command)
        return original(command, *args, **kwargs)

    mock_run_command.side_effect = tracking

    build_image(build_args="APT_PACKAGES=jq curl")

    assert len(build_calls) == 1
    base_build_cmd = build_calls[0]
    assert any("APT_PACKAGES=jq curl" in str(a) for a in base_build_cmd)


def test_container_shell_selects_most_recent_tag(
    temp_project_dir,
    mock_run_command,
    mock_load_data_file,
    mock_get_package_name,
):
    """When `tag` is None, `container_shell` should pick the most-recently-built tag (no build)."""
    from common_python_tasks.tasks import container_shell

    run_calls: list[list[str]] = []
    original = mock_run_command.side_effect

    def tracking(command, *args, **kwargs):
        # Provide fake `docker image ls` output (newest first)
        if len(command) >= 3 and command[:3] == ["docker", "image", "ls"]:
            result = original(command, *args, **kwargs)
            result.stdout = (
                "docker.io/test-package:abc123\n" "docker.io/test-package:1.0.0\n"
            )
            return result
        if "docker" in command and "run" in command:
            run_calls.append(command)
        return original(command, *args, **kwargs)

    mock_run_command.side_effect = tracking

    container_shell()

    assert len(run_calls) == 1
    assert any("test-package:abc123" in " ".join(map(str, c)) for c in run_calls)


def test_container_shell_fails_when_no_images(
    temp_project_dir,
    mock_run_command,
    mock_load_data_file,
    mock_get_package_name,
):
    """`container_shell` should exit when no built images exist and `tag` is None."""
    from common_python_tasks.tasks import container_shell

    original = mock_run_command.side_effect

    def tracking(command, *args, **kwargs):
        if len(command) >= 3 and command[:3] == ["docker", "image", "ls"]:
            result = original(command, *args, **kwargs)
            result.stdout = ""
            return result
        return original(command, *args, **kwargs)

    mock_run_command.side_effect = tracking

    with pytest.raises(SystemExit):
        container_shell()
