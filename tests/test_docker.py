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
        from common_python_tasks.docker import build_image

        dockerignore_path = temp_project_dir / ".dockerignore"
        assert not dockerignore_path.exists()

        build_image(
            dockerfile_path=None,
            dockerfile_text="FROM python:3.11\n",
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
        from common_python_tasks.docker import build_image

        dockerignore_path = temp_project_dir / ".dockerignore"
        original_content = "# Custom dockerignore\n*.log\n"
        dockerignore_path.write_text(original_content)

        build_image(
            dockerfile_path=None,
            dockerfile_text="FROM python:3.11\n",
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
        from common_python_tasks.docker import build_image

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

        build_image(
            dockerfile_path=None,
            dockerfile_text="FROM python:3.11\n",
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
        from common_python_tasks.docker import build_image

        dockerignore_path = temp_project_dir / ".dockerignore"
        temporary_dockerfile_path = None

        def failing_side_effect(command, *args, **kwargs):
            nonlocal temporary_dockerfile_path
            result = MagicMock(spec=subprocess.CompletedProcess)
            if "docker" in command and "build" in command:
                temporary_dockerfile_path = Path(command[command.index("-f") + 1])
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
            elif command[:2] == ["uv", "--version"]:
                result.stdout = "uv 0.8.0"
            else:
                result.stdout = ""
            return result

        mock_run_command.side_effect = failing_side_effect

        with pytest.raises(SystemExit):
            build_image(
                dockerfile_path=None,
                dockerfile_text="FROM python:3.11\n",
                context_path=temp_project_dir,
            )

        assert not dockerignore_path.exists()
        assert temporary_dockerfile_path is not None
        assert not temporary_dockerfile_path.exists()

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
        from common_python_tasks.docker import build_image

        dockerignore_path = temp_project_dir / ".dockerignore"
        expected_content = "*\n!pyproject.toml\n!uv.lock\n!README.md\n!LICENSE\n\n!src\n"

        actual_content = None
        original_run_command = mock_run_command.side_effect

        def tracking_side_effect(command, *args, **kwargs):
            nonlocal actual_content
            if (
                "docker" in command
                and "build" in command
                and dockerignore_path.exists()
            ):
                actual_content = dockerignore_path.read_text()
            return original_run_command(command, *args, **kwargs)

        mock_run_command.side_effect = tracking_side_effect

        build_image(
            dockerfile_path=None,
            dockerfile_text="FROM python:3.11\n",
            context_path=temp_project_dir,
        )

        assert actual_content == expected_content

    def test_render_build_image_does_not_remove_dist_before_build(
        self,
        temp_project_dir: Path,
        mock_run_command: MagicMock,
        mock_get_image_tag: MagicMock,
        mock_get_authors: MagicMock,
        mock_get_package_name: MagicMock,
        mock_remove_path: MagicMock,
    ):
        """Test that render_build_image does not delete the host dist directory."""
        from common_python_tasks.docker import render_build_image

        dist_path = temp_project_dir / "dist"
        dist_path.mkdir()
        (dist_path / "package.whl").write_text("content")

        render_build_image(
            dockerfile_text="FROM python:3.11\n",
            context_path=temp_project_dir,
        )

        mock_remove_path.assert_not_called()


class TestRenderBuildImage:
    """Tests for render-only Docker image plans."""

    def test_render_build_image_returns_full_command_and_temp_dockerfile(
        self,
        temp_project_dir: Path,
        mock_run_command: MagicMock,
        mock_get_image_tag: MagicMock,
        mock_get_authors: MagicMock,
        mock_get_package_name: MagicMock,
    ):
        """Test that render mode returns the exact build command and keeps the generated Dockerfile."""
        from common_python_tasks.docker import render_build_image

        plan = render_build_image(
            dockerfile_text="FROM python:3.11\n",
            context_path=temp_project_dir,
        )

        assert Path(plan.dockerfile_path).exists()
        assert plan.dockerfile_text == "FROM python:3.11\n"
        assert plan.command[:3] == [
            "docker",
            "build",
            "-f",
        ]
        assert plan.command_display.startswith("docker build ")
        assert str(plan.dockerfile_path) in plan.command_display
        assert plan.command[-1] == str(temp_project_dir)

    def test_render_build_image_includes_native_docker_build_args(
        self,
        temp_project_dir: Path,
        mock_run_command: MagicMock,
        mock_get_image_tag: MagicMock,
        mock_get_authors: MagicMock,
        mock_get_package_name: MagicMock,
    ):
        """Test that render mode passes native arguments before the build context."""
        from common_python_tasks.docker import render_build_image

        plan = render_build_image(
            dockerfile_text="FROM python:3.11\n",
            context_path=temp_project_dir,
            docker_build_args=[
                "--secret",
                "id=pip_conf,env=PIP_CONF",
                "--add-host",
                "example:127.0.0.1",
            ],
        )

        assert plan.command[-5:] == [
            "--secret",
            "id=pip_conf,env=PIP_CONF",
            "--add-host",
            "example:127.0.0.1",
            str(temp_project_dir),
        ]

    def test_render_build_image_executes_hook_before_build_planning(
        self,
        temp_project_dir: Path,
        mock_run_command: MagicMock,
        mock_get_image_tag: MagicMock,
        mock_get_authors: MagicMock,
        mock_get_package_name: MagicMock,
    ):
        """Test that a dockerfile hook can mutate generated content before planning."""
        from common_python_tasks.docker import render_build_image

        hook_path = temp_project_dir / "hook.sh"
        hook_path.write_text("#!/bin/sh\n", encoding="utf-8")
        hook_path.chmod(0o755)

        original_side_effect = mock_run_command.side_effect

        def tracking_side_effect(command, *args, **kwargs):
            if command and str(command[0]) == str(hook_path):
                dockerfile_path = Path(command[1])
                dockerfile_path.write_text(
                    dockerfile_path.read_text(encoding="utf-8") + "RUN echo hooked\n",
                    encoding="utf-8",
                )
            return original_side_effect(command, *args, **kwargs)

        mock_run_command.side_effect = tracking_side_effect

        plan = render_build_image(
            dockerfile_text="FROM python:3.11\n",
            context_path=temp_project_dir,
            dockerfile_hook_path=hook_path,
        )

        assert "RUN echo hooked" in plan.dockerfile_text


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
        from common_python_tasks.docker import build_image

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

        build_image(
            dockerfile_path=None,
            dockerfile_text="FROM python:3.11\n",
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
        from common_python_tasks.docker import build_image

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

        build_image(
            dockerfile_path=None,
            dockerfile_text="FROM python:3.11\n",
            context_path=temp_project_dir,
        )

        assert build_command is not None
        tag_args = [
            build_command[i + 1]
            for i, arg in enumerate(build_command)
            if arg == "-t" and i + 1 < len(build_command)
        ]
        assert not any("latest" in tag for tag in tag_args)


def test_build_image_preserves_non_empty_dist_directory_before_build(
    temp_project_dir,
    mock_load_data_file,
    mock_run_command,
    mock_get_image_tag,
    mock_get_authors,
    mock_get_package_name,
):
    from common_python_tasks.docker import build_image

    dist_dir = temp_project_dir / "dist"
    dist_dir.mkdir()
    (dist_dir / "artifact.whl").write_text("wheel")

    build_calls = []
    original = mock_run_command.side_effect

    def tracking(command, *args, **kwargs):
        if "docker" in command and "build" in command:
            build_calls.append(command)
        return original(command, *args, **kwargs)

    mock_run_command.side_effect = tracking

    build_image(dockerfile_text="FROM python:3.11\n", context_path=temp_project_dir)

    assert dist_dir.exists()
    assert len(build_calls) == 1


class TestBuildDepsImage:
    """Tests for build_deps_image building and tagging flow."""

    def test_builds_deps_image_and_returns_tag(
        self,
        mock_run_command,
        mock_load_data_file,
        mock_get_package_name,
        monkeypatch,
    ):
        monkeypatch.delenv("CONTAINER_PYTHON_VARIANT", raising=False)

        from common_python_tasks.docker import build_deps_image

        tag = build_deps_image("RUN apt-get install -y curl", single_arch=True)
        assert tag.startswith("test-package-deps:deps-")
        docker_calls = [
            c
            for c in mock_run_command.call_args_list
            if c[0][0][0] == "docker" and c[0][0][1] == "build"
        ]
        assert len(docker_calls) == 1
        assert "PYTHON_VARIANT=slim" in [str(arg) for arg in docker_calls[0][0][0]]

    def test_builds_deps_image_from_dockerfile_path(
        self,
        tmp_path,
        mock_run_command,
        mock_load_data_file,
        mock_get_package_name,
    ):
        from common_python_tasks.docker import build_deps_image

        deps_file = tmp_path / "Dockerfile.deps"
        deps_file.write_text(
            "FROM python:3.11\nRUN mkdir -p /tmp/deps\nRUN echo hi >/tmp/deps/dep1\n",
            encoding="utf-8",
        )

        tag = build_deps_image(
            deps_content=None,
            deps_dockerfile_path=deps_file,
            single_arch=True,
        )
        assert tag.startswith("test-package-deps:deps-")
        docker_calls = [
            c
            for c in mock_run_command.call_args_list
            if c[0][0][0] == "docker" and c[0][0][1] == "build"
        ]
        assert len(docker_calls) == 1

    def test_builds_deps_image_with_no_cache_uses_cache_id_suffix_arg(
        self,
        mock_run_command,
        mock_load_data_file,
        mock_get_package_name,
    ):
        from common_python_tasks.docker import build_deps_image

        build_deps_image(
            "RUN apt-get install -y curl",
            no_cache=True,
            single_arch=True,
            cache_id_suffix="-abc123",
        )

        docker_calls = [
            c
            for c in mock_run_command.call_args_list
            if c[0][0][0] == "docker" and c[0][0][1] == "build"
        ]
        assert len(docker_calls) == 1
        command = docker_calls[0][0][0]
        assert "--no-cache" in command
        assert "CACHE_ID_SUFFIX=-abc123" in [
            str(arg) for arg in command if arg is not None
        ]

    def test_builds_deps_image_from_multiple_dockerfile_paths(
        self,
        tmp_path,
        mock_run_command,
        mock_load_data_file,
        mock_get_package_name,
    ):
        from common_python_tasks.docker import build_deps_image

        deps_file1 = tmp_path / "Dockerfile.deps.1"
        deps_file1.write_text(
            "FROM python:3.11\nRUN mkdir -p /tmp/deps\nRUN echo hi >/tmp/deps/dep1\n",
            encoding="utf-8",
        )
        deps_file2 = tmp_path / "Dockerfile.deps.2"
        deps_file2.write_text(
            "RUN echo more >>/tmp/deps/dep1\n",
            encoding="utf-8",
        )

        tag = build_deps_image(
            deps_content=None,
            deps_dockerfile_path=[deps_file1, deps_file2],
            single_arch=True,
        )
        assert tag.startswith("test-package-deps:deps-")
        docker_calls = [
            c
            for c in mock_run_command.call_args_list
            if c[0][0][0] == "docker" and c[0][0][1] == "build"
        ]
        assert len(docker_calls) == 1

    def test_tag_varies_with_content(
        self,
        mock_run_command,
        mock_load_data_file,
        mock_get_package_name,
    ):
        from common_python_tasks.docker import build_deps_image

        tag1 = build_deps_image("RUN apt-get install -y curl", single_arch=True)
        tag2 = build_deps_image("RUN apt-get install -y wget", single_arch=True)
        assert tag1 != tag2

    def test_same_content_gives_same_tag(
        self,
        mock_run_command,
        mock_load_data_file,
        mock_get_package_name,
    ):
        from common_python_tasks.docker import build_deps_image

        content = "RUN apt-get install -y jq"
        tag1 = build_deps_image(content, single_arch=True)
        tag2 = build_deps_image(content, single_arch=True)
        assert tag1 == tag2


class TestBuildExtensionImage:
    """Tests for build_extension_image delegation behavior."""

    def test_extension_image_uses_base_and_omits_target(
        self,
        temp_project_dir,
        mock_run_command,
        mock_load_data_file,
        mock_get_image_tag,
        mock_get_authors,
        mock_get_package_name,
    ):
        from common_python_tasks.docker import build_extension_image

        captured: dict[str, str | list[str]] = {}
        original_side_effect = mock_run_command.side_effect

        def tracking(command, *args, **kwargs):
            if "docker" in command and "build" in command:
                captured["command"] = command
                if "-f" in command:
                    dockerfile_path = command[command.index("-f") + 1]
                    captured["dockerfile_text"] = Path(dockerfile_path).read_text(
                        encoding="utf-8"
                    )
            return original_side_effect(command, *args, **kwargs)

        mock_run_command.side_effect = tracking

        build_extension_image(
            base_full_name="ghcr.io/example/base-image",
            base_version_tag="1.2.3",
            extension_content="RUN echo extension-installed",
            context_path=temp_project_dir,
            image_name_override="custom-extension-image",
            single_arch=True,
        )

        build_command = [str(arg) for arg in captured["command"] if arg is not None]
        assert "--target" not in build_command
        assert any("custom-extension-image:" in arg for arg in build_command)

        dockerfile_text = str(captured["dockerfile_text"])
        assert "FROM ghcr.io/example/base-image:1.2.3" in dockerfile_text
        assert "RUN echo extension-installed" in dockerfile_text

    def test_extension_image_passes_extra_build_args(
        self,
        temp_project_dir,
        mock_run_command,
        mock_load_data_file,
        mock_get_image_tag,
        mock_get_authors,
        mock_get_package_name,
    ):
        from common_python_tasks.docker import build_extension_image

        captured_command = []
        original_side_effect = mock_run_command.side_effect

        def tracking(command, *args, **kwargs):
            nonlocal captured_command
            if "docker" in command and "build" in command:
                captured_command = [str(arg) for arg in command if arg is not None]
            return original_side_effect(command, *args, **kwargs)

        mock_run_command.side_effect = tracking

        build_extension_image(
            base_full_name="ghcr.io/example/base-image",
            base_version_tag="1.2.3",
            extension_content="RUN echo extension-installed",
            context_path=temp_project_dir,
            single_arch=True,
            extra_build_args={"MY_CUSTOM_ARG": "my-value"},
        )

        assert "--build-arg" in captured_command
        assert "MY_CUSTOM_ARG=my-value" in captured_command


def test_prune_images_keep_handles_full_and_short_references(mock_run_command):
    """`prune_images_keep` should delete old tags for both short and full refs."""
    from common_python_tasks.docker import prune_images_keep

    removed_refs: list[str] = []

    def side_effect(command, *args, **kwargs):
        result = MagicMock(spec=subprocess.CompletedProcess)
        result.returncode = 0
        result.stdout = ""

        if command[:3] == ["docker", "image", "ls"]:
            reference_filter = command[command.index("--filter") + 1]
            if reference_filter == "reference=ghcr.io/acme/test-package:*":
                result.stdout = (
                    "ghcr.io/acme/test-package:latest\n"
                    "ghcr.io/acme/test-package:older-tag\n"
                    "ghcr.io/acme/test-package:old-tag\n"
                )
            elif reference_filter == "reference=test-package:*":
                result.stdout = (
                    "test-package:latest\n"
                    "test-package:older-tag\n"
                    "test-package:old-tag\n"
                )

        if command[:2] == ["docker", "rmi"]:
            removed_refs.append(command[2])

        return result

    mock_run_command.side_effect = side_effect

    prune_images_keep(
        "ghcr.io/acme/test-package",
        "test-package",
        0,
        protect_tags=["latest"],
    )

    assert removed_refs == [
        "test-package:old-tag",
        "ghcr.io/acme/test-package:old-tag",
    ]
