import logging
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestParseContainerExtensions:
    """Tests for _parse_container_extensions parameter parsing."""

    def test_plain_bundle_name(self, monkeypatch):
        from common_python_tasks.utils import parse_container_extensions

        monkeypatch.delenv("CONTAINER_EXTENSION_FILES", raising=False)
        monkeypatch.setenv("CONTAINER_EXTENSIONS", "some_ext")

        result = parse_container_extensions()
        assert len(result) == 1
        assert result[0]["id"] == "some_ext"
        assert result[0]["bundle_name"] == "some_ext"
        assert result[0]["args"] is None

    def test_parameterised_bundle(self, monkeypatch):
        from common_python_tasks.utils import parse_container_extensions

        monkeypatch.delenv("CONTAINER_EXTENSION_FILES", raising=False)
        monkeypatch.setenv("CONTAINER_EXTENSIONS", "some_ext=jq curl")

        result = parse_container_extensions()
        assert len(result) == 1
        assert result[0]["id"] == "some_ext"
        assert result[0]["bundle_name"] == "some_ext"
        assert result[0]["args"] == "jq curl"

    def test_mixed_parameterised_and_plain(self, monkeypatch):
        from common_python_tasks.utils import parse_container_extensions

        monkeypatch.delenv("CONTAINER_EXTENSION_FILES", raising=False)
        monkeypatch.setenv("CONTAINER_EXTENSIONS", "some_ext=jq curl wget:plain_ext")

        result = parse_container_extensions()
        assert len(result) == 2
        assert result[0]["id"] == "some_ext"
        assert result[0]["args"] == "jq curl wget"
        assert result[1]["id"] == "plain_ext"
        assert result[1]["args"] is None

    def test_empty_args_treated_as_empty_string(self, monkeypatch):
        from common_python_tasks.utils import parse_container_extensions

        monkeypatch.delenv("CONTAINER_EXTENSION_FILES", raising=False)
        monkeypatch.setenv("CONTAINER_EXTENSIONS", "some_ext=")

        result = parse_container_extensions()
        assert len(result) == 1
        assert result[0]["args"] == ""


class TestResolveExtensionContent:
    """Tests for _resolve_extension_content (no template substitution).

    Argument passing is now handled via Docker build-args; this function only
    returns the fragment content unchanged.
    """

    def test_template_contains_build_arg_variable(self, mock_load_data_file):
        from common_python_tasks.utils import resolve_extension_content

        desc = {
            "id": "template_bundle",
            "source": "bundle",
            "path": None,
            "bundle_name": "template_bundle",
            "args": "jq curl",
        }
        content = resolve_extension_content(desc)
        assert "APT_PACKAGES" in content
        assert "jq curl" not in content

    def test_missing_args_do_not_affect_content(self, mock_load_data_file):
        from common_python_tasks.utils import resolve_extension_content

        desc = {
            "id": "template_bundle",
            "source": "bundle",
            "path": None,
            "bundle_name": "template_bundle",
            "args": None,
        }
        # Should simply return the template content (argument application
        # happens at build time)
        content = resolve_extension_content(desc)
        assert "APT_PACKAGES" in content

    def test_file_extension_without_placeholder_and_no_args(self, tmp_path):
        from common_python_tasks.utils import resolve_extension_content

        ext_file = tmp_path / "Dockerfile.custom"
        ext_file.write_text("RUN echo hello\n")

        desc = {
            "id": "custom",
            "source": "file",
            "path": str(ext_file),
            "bundle_name": None,
            "args": None,
        }
        content = resolve_extension_content(desc)
        assert content == "RUN echo hello\n"


class TestDockerignoreHandling:
    """Tests for .dockerignore file handling during image builds."""

    @pytest.fixture(autouse=True)
    def mock_installed_requirement_version(self):
        with patch(
            "common_python_tasks.utils.get_installed_requirement_version"
        ) as mock:
            mock.side_effect = lambda name: {
                "poetry-dynamic-versioning[plugin]": "0.17.0",
                "poetry-plugin-export": "1.5.0",
                "tomlkit": "0.12.1",
            }.get(name)
            yield mock

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
        from common_python_tasks.utils import build_image

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
        from common_python_tasks.utils import build_image

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
        from common_python_tasks.utils import build_image

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
        from common_python_tasks.utils import build_image

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
            build_image(
                dockerfile_path=None,
                dockerfile_text="FROM python:3.11\n",
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
        from common_python_tasks.utils import build_image

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

        build_image(
            dockerfile_path=None,
            dockerfile_text="FROM python:3.11\n",
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
        from common_python_tasks.utils import build_image

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
        from common_python_tasks.utils import build_image

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


def test_build_with_multiple_extensions(
    temp_project_dir,
    mock_run_command,
    mock_load_data_file,
    mock_get_image_tag,
    mock_get_authors,
    mock_get_package_name,
    monkeypatch,
):
    """Building with multiple extension Dockerfiles should build base + extensions.

    Use local `Dockerfile.<name>` fixtures (not bundled test fragments).
    """
    from common_python_tasks.tasks import build_image

    ext1 = temp_project_dir / "Dockerfile.ext1"
    ext1.write_text("# ext1\nRUN echo ext1\n")
    ext2 = temp_project_dir / "Dockerfile.ext2"
    ext2.write_text("# ext2\nRUN echo ext2\n")

    monkeypatch.setenv("CONTAINER_EXTENSION_FILES", "Dockerfile.ext1:Dockerfile.ext2")
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

    # Expect a single Docker build invocation with extensions injected into the base image
    assert len(build_calls) == 1


def test_render_template_text_injects_extension_content():
    from common_python_tasks.utils import render_template_text

    template = (
        "FROM runtime\n{{ EXTENSION_CONTENT|default('') }}\nFROM runtime AS debug\n"
    )
    rendered = render_template_text(
        template,
        {"EXTENSION_CONTENT": "# ext1\nRUN echo ext1\n"},
    )

    assert "RUN echo ext1" in rendered
    assert rendered.index("RUN echo ext1") < rendered.index("FROM runtime AS debug")


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

    ext = temp_project_dir / "Dockerfile.ext1"
    ext.write_text("# ext1\nRUN echo ext1\n")

    monkeypatch.setenv("CONTAINER_EXTENSION_FILES", "Dockerfile.ext1")
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

    Use local extension Dockerfile fixtures instead of bundled test fragments.
    """
    from common_python_tasks.tasks import build_image

    ext1 = temp_project_dir / "Dockerfile.ext1"
    ext1.write_text("# ext1\nRUN echo ext1\n")
    ext2 = temp_project_dir / "Dockerfile.ext2"
    ext2.write_text("# ext2\nRUN echo ext2\n")

    monkeypatch.setenv("CONTAINER_EXTENSION_FILES", "Dockerfile.ext1:Dockerfile.ext2")
    monkeypatch.setenv("CONTAINER_PRUNE_KEEP", "0")

    original = mock_run_command.side_effect

    def failing_side_effect(command, *args, **kwargs):
        if "docker" in command and "build" in command:
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
    """CONTAINER_BUILD_ARGS should drive template-rendered apt package installation."""
    from common_python_tasks.tasks import build_image

    monkeypatch.setenv("CONTAINER_BUILD_ARGS", "APT_PACKAGES=jq")

    original_load_data_file = mock_load_data_file.side_effect

    def load_data_file_with_apt(
        filename, type_identifier="generic", fatal_on_missing=True
    ):
        if filename == "Dockerfile.j2":
            return (
                "/fake/path/Dockerfile.j2",
                "FROM python:3.11\n"
                "{% if APT_PACKAGES %}\n"
                "RUN apt-get update && apt-get install -y --no-install-recommends {{ APT_PACKAGES }}\n"
                "{% endif %}\n",
            )
        return original_load_data_file(filename, type_identifier, fatal_on_missing)

    mock_load_data_file.side_effect = load_data_file_with_apt

    build_calls: list[list[str]] = []
    captured_dockerfile: dict[str, str] = {}
    original = mock_run_command.side_effect

    def tracking(command, *args, **kwargs):
        if "docker" in command and "build" in command:
            build_calls.append(command)
            dockerfile_path = command[command.index("-f") + 1]
            captured_dockerfile["content"] = Path(dockerfile_path).read_text(
                encoding="utf-8"
            )
        return original(command, *args, **kwargs)

    mock_run_command.side_effect = tracking

    build_image()

    # Only the base build should run (no extra extension image)
    assert len(build_calls) == 1

    # Ensure apt packages are rendered into the Dockerfile template, not generic build args
    base_build_cmd = build_calls[0]
    assert (
        "apt-get install -y --no-install-recommends jq"
        in captured_dockerfile["content"]
    )
    assert "ARG APT_PACKAGES" not in captured_dockerfile["content"]
    assert not any("APT_PACKAGES=jq" in str(a) for a in base_build_cmd)


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

    original_load_data_file = mock_load_data_file.side_effect

    def load_data_file_with_apt(
        filename, type_identifier="generic", fatal_on_missing=True
    ):
        if filename == "Dockerfile.j2":
            return (
                "/fake/path/Dockerfile.j2",
                "FROM python:3.11\n"
                "{% if APT_PACKAGES %}\n"
                "RUN apt-get update && apt-get install -y --no-install-recommends {{ APT_PACKAGES }}\n"
                "{% endif %}\n",
            )
        return original_load_data_file(filename, type_identifier, fatal_on_missing)

    mock_load_data_file.side_effect = load_data_file_with_apt

    build_calls: list[list[str]] = []
    captured_dockerfile: dict[str, str] = {}
    original = mock_run_command.side_effect

    def tracking(command, *args, **kwargs):
        if "docker" in command and "build" in command:
            build_calls.append(command)
            dockerfile_path = command[command.index("-f") + 1]
            captured_dockerfile["content"] = Path(dockerfile_path).read_text(
                encoding="utf-8"
            )
        return original(command, *args, **kwargs)

    mock_run_command.side_effect = tracking

    build_image()

    # Verify the apt package list is rendered into the generated Dockerfile
    assert len(build_calls) == 1
    base_build_cmd = build_calls[0]
    assert (
        "apt-get install -y --no-install-recommends jq curl"
        in captured_dockerfile["content"]
    )
    assert not any("APT_PACKAGES=jq curl" in str(a) for a in base_build_cmd)


def test_build_image_injects_container_env_from_containerenv_file(
    temp_project_dir,
    mock_run_command,
    mock_load_data_file,
    mock_get_image_tag,
    mock_get_authors,
    mock_get_package_name,
):
    from common_python_tasks.tasks import build_image

    (temp_project_dir / ".containerenv").write_text(
        'FOO=bar BAZ="hello world"\n', encoding="utf-8"
    )

    original_load_data_file = mock_load_data_file.side_effect

    def load_data_file_with_env(
        filename, type_identifier="generic", fatal_on_missing=True
    ):
        if filename == "Dockerfile.j2":
            return (
                "/fake/path/Dockerfile.j2",
                "FROM python:3.11\n"
                "{% if CONTAINER_ENV_VARS %}\n"
                "{% for env_var in CONTAINER_ENV_VARS %}\n"
                "ENV {{ env_var }}\n"
                "{% endfor %}\n"
                "{% endif %}\n",
            )
        return original_load_data_file(filename, type_identifier, fatal_on_missing)

    mock_load_data_file.side_effect = load_data_file_with_env

    build_calls: list[list[str]] = []
    captured_dockerfile: dict[str, str] = {}
    original = mock_run_command.side_effect

    def tracking(command, *args, **kwargs):
        if "docker" in command and "build" in command:
            build_calls.append(command)
            dockerfile_path = command[command.index("-f") + 1]
            captured_dockerfile["content"] = Path(dockerfile_path).read_text(
                encoding="utf-8"
            )
        return original(command, *args, **kwargs)

    mock_run_command.side_effect = tracking

    build_image()

    assert len(build_calls) == 1
    assert "ENV FOO=bar" in captured_dockerfile["content"]
    assert "ENV BAZ=hello world" in captured_dockerfile["content"]
    assert not any("FOO=bar" in str(a) for a in build_calls[0])
    assert not any("BAZ=hello world" in str(a) for a in build_calls[0])


def test_build_image_container_env_precedence_overrides_file_with_env_and_cli(
    temp_project_dir,
    mock_run_command,
    mock_load_data_file,
    mock_get_image_tag,
    mock_get_authors,
    mock_get_package_name,
    monkeypatch,
):
    from common_python_tasks.tasks import build_image

    (temp_project_dir / ".containerenv").write_text(
        "SOURCE=containerenv\n", encoding="utf-8"
    )
    monkeypatch.setenv("CONTAINER_ENV", "SOURCE=env")

    original_load_data_file = mock_load_data_file.side_effect

    def load_data_file_with_env(
        filename, type_identifier="generic", fatal_on_missing=True
    ):
        if filename == "Dockerfile.j2":
            return (
                "/fake/path/Dockerfile.j2",
                "FROM python:3.11\n"
                "{% if CONTAINER_ENV_VARS %}\n"
                "{% for env_var in CONTAINER_ENV_VARS %}\n"
                "ENV {{ env_var }}\n"
                "{% endfor %}\n"
                "{% endif %}\n",
            )
        return original_load_data_file(filename, type_identifier, fatal_on_missing)

    mock_load_data_file.side_effect = load_data_file_with_env

    build_calls: list[list[str]] = []
    captured_dockerfile: dict[str, str] = {}
    original = mock_run_command.side_effect

    def tracking(command, *args, **kwargs):
        if "docker" in command and "build" in command:
            build_calls.append(command)
            dockerfile_path = command[command.index("-f") + 1]
            captured_dockerfile["content"] = Path(dockerfile_path).read_text(
                encoding="utf-8"
            )
        return original(command, *args, **kwargs)

    mock_run_command.side_effect = tracking

    build_image(container_env="SOURCE=cli")

    assert len(build_calls) == 1
    assert "ENV SOURCE=containerenv" in captured_dockerfile["content"]
    assert "ENV SOURCE=env" in captured_dockerfile["content"]
    assert "ENV SOURCE=cli" in captured_dockerfile["content"]
    assert captured_dockerfile["content"].strip().endswith("ENV SOURCE=cli")
    assert not any("SOURCE=cli" in str(a) for a in build_calls[0])


def test_build_image_reads_container_envfile_path_overrides_dotcontainerenv(
    temp_project_dir,
    mock_run_command,
    mock_load_data_file,
    mock_get_image_tag,
    mock_get_authors,
    mock_get_package_name,
    monkeypatch,
):
    from common_python_tasks.tasks import build_image

    (temp_project_dir / ".containerenv").write_text(
        "SOURCE=containerenv\n", encoding="utf-8"
    )
    envfile_path = temp_project_dir / "mycontainer.env"
    envfile_path.write_text("SOURCE=envfile\n", encoding="utf-8")

    original_load_data_file = mock_load_data_file.side_effect

    def load_data_file_with_env(
        filename, type_identifier="generic", fatal_on_missing=True
    ):
        if filename == "Dockerfile.j2":
            return (
                "/fake/path/Dockerfile.j2",
                "FROM python:3.11\n"
                "{% if CONTAINER_ENV_VARS %}\n"
                "{% for env_var in CONTAINER_ENV_VARS %}\n"
                "ENV {{ env_var }}\n"
                "{% endfor %}\n"
                "{% endif %}\n",
            )
        return original_load_data_file(filename, type_identifier, fatal_on_missing)

    mock_load_data_file.side_effect = load_data_file_with_env

    build_calls: list[list[str]] = []
    captured_dockerfile: dict[str, str] = {}
    original = mock_run_command.side_effect

    def tracking(command, *args, **kwargs):
        if "docker" in command and "build" in command:
            build_calls.append(command)
            dockerfile_path = command[command.index("-f") + 1]
            captured_dockerfile["content"] = Path(dockerfile_path).read_text(
                encoding="utf-8"
            )
        return original(command, *args, **kwargs)

    mock_run_command.side_effect = tracking

    build_image(container_envfile=str(envfile_path))

    assert len(build_calls) == 1
    assert "ENV SOURCE=containerenv" in captured_dockerfile["content"]
    assert "ENV SOURCE=envfile" in captured_dockerfile["content"]
    assert captured_dockerfile["content"].strip().endswith("ENV SOURCE=envfile")
    assert not any("SOURCE=envfile" in str(a) for a in build_calls[0])


def test_build_image_reads_multiple_container_envfiles_in_order(
    temp_project_dir,
    mock_run_command,
    mock_load_data_file,
    mock_get_image_tag,
    mock_get_authors,
    mock_get_package_name,
):
    from common_python_tasks.tasks import build_image

    envfile_path_1 = temp_project_dir / "first.env"
    envfile_path_1.write_text("A=one:B=two", encoding="utf-8")
    envfile_path_2 = temp_project_dir / "second.env"
    envfile_path_2.write_text("C=three:D=four", encoding="utf-8")

    original_load_data_file = mock_load_data_file.side_effect

    def load_data_file_with_env(
        filename, type_identifier="generic", fatal_on_missing=True
    ):
        if filename == "Dockerfile.j2":
            return (
                "/fake/path/Dockerfile.j2",
                "FROM python:3.11\n"
                "{% if CONTAINER_ENV_VARS %}\n"
                "{% for env_var in CONTAINER_ENV_VARS %}\n"
                "ENV {{ env_var }}\n"
                "{% endfor %}\n"
                "{% endif %}\n",
            )
        return original_load_data_file(filename, type_identifier, fatal_on_missing)

    mock_load_data_file.side_effect = load_data_file_with_env

    build_calls: list[list[str]] = []
    captured_dockerfile: dict[str, str] = {}
    original = mock_run_command.side_effect

    def tracking(command, *args, **kwargs):
        if "docker" in command and "build" in command:
            build_calls.append(command)
            dockerfile_path = command[command.index("-f") + 1]
            captured_dockerfile["content"] = Path(dockerfile_path).read_text(
                encoding="utf-8"
            )
        return original(command, *args, **kwargs)

    mock_run_command.side_effect = tracking

    build_image(container_envfile=f"{envfile_path_1}:{envfile_path_2}")

    assert len(build_calls) == 1
    assert "ENV A=one" in captured_dockerfile["content"]
    assert "ENV B=two" in captured_dockerfile["content"]
    assert "ENV C=three" in captured_dockerfile["content"]
    assert "ENV D=four" in captured_dockerfile["content"]
    assert captured_dockerfile["content"].index("ENV A=one") < captured_dockerfile[
        "content"
    ].index("ENV C=three")
    assert not any("A=one" in str(a) for a in build_calls[0])


def test_build_image_passes_required_dependency_versions(
    temp_project_dir,
    mock_run_command,
    mock_load_data_file,
    mock_get_image_tag,
    mock_get_authors,
    mock_get_package_name,
):
    import os
    from unittest.mock import patch

    from common_python_tasks.tasks import build_image

    os.environ.pop("CONTAINER_BUILD_ARGS", None)

    with patch(
        "common_python_tasks.utils.get_installed_requirement_version",
        side_effect=lambda name: {
            "poetry-dynamic-versioning[plugin]": "0.17.0",
            "poetry-plugin-export": "1.5.0",
            "tomlkit": "0.12.1",
        }.get(name),
    ):
        build_calls: list[list[str]] = []
        original = mock_run_command.side_effect

        def tracking(command, *args, **kwargs):
            if "docker" in command and "build" in command:
                build_calls.append(command)
            return original(command, *args, **kwargs)

        mock_run_command.side_effect = tracking

        build_image()

    assert len(build_calls) == 1
    base_build_cmd = build_calls[0]
    assert any(
        "POETRY_DYNAMIC_VERSIONING_PLUGIN_VERSION=0.17.0" in str(a)
        for a in base_build_cmd
    )
    assert any("POETRY_PLUGIN_EXPORT_VERSION=1.5.0" in str(a) for a in base_build_cmd)
    assert any("TOMLKIT_VERSION=0.12.1" in str(a) for a in base_build_cmd)


def test_build_image_no_cache_passes_no_cache_pull_and_plain(
    temp_project_dir,
    mock_run_command,
    mock_load_data_file,
    mock_get_image_tag,
    mock_get_authors,
    mock_get_package_name,
):
    from common_python_tasks.tasks import build_image

    build_calls: list[list[str]] = []
    original = mock_run_command.side_effect

    def tracking(command, *args, **kwargs):
        if "docker" in command and "build" in command:
            build_calls.append(command)
        return original(command, *args, **kwargs)

    mock_run_command.side_effect = tracking

    build_image(no_cache=True, plain=True)

    assert len(build_calls) == 1
    base_build_cmd = [str(a) for a in build_calls[0] if a is not None]
    assert "--progress" in base_build_cmd
    assert "plain" in base_build_cmd
    assert "--no-cache" in base_build_cmd
    assert "--pull" in base_build_cmd
    assert not any(a.startswith("CACHE_ID_SUFFIX=") for a in base_build_cmd)


def test_build_image_accepts_build_args_param_for_real_docker_arg(
    temp_project_dir,
    mock_run_command,
    mock_load_data_file,
    mock_get_image_tag,
    mock_get_authors,
    mock_get_package_name,
):
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

    build_image(build_args="POETRY_VERSION=9.9.9")

    assert len(build_calls) == 1
    base_build_cmd = build_calls[0]
    assert any("POETRY_VERSION=9.9.9" in str(a) for a in base_build_cmd)
    assert not any("POETRY_VERSION=1.8.0" in str(a) for a in base_build_cmd)


def test_build_image_includes_workdir_path_from_env(
    temp_project_dir,
    mock_run_command,
    mock_load_data_file,
    mock_get_image_tag,
    mock_get_authors,
    mock_get_package_name,
    monkeypatch,
):
    from common_python_tasks.tasks import build_image

    monkeypatch.setenv("WORKDIR_PATH", "/app")
    monkeypatch.delenv("CONTAINER_BUILD_ARGS", raising=False)

    build_calls: list[list[str]] = []
    original = mock_run_command.side_effect

    def tracking(command, *args, **kwargs):
        if "docker" in command and "build" in command:
            build_calls.append(command)
        return original(command, *args, **kwargs)

    mock_run_command.side_effect = tracking

    build_image()

    assert len(build_calls) == 1
    base_build_cmd = build_calls[0]
    assert any("WORKDIR_PATH=/app" in str(a) for a in base_build_cmd)


def test_build_image_explicit_workdir_path_build_arg_overrides_env(
    temp_project_dir,
    mock_run_command,
    mock_load_data_file,
    mock_get_image_tag,
    mock_get_authors,
    mock_get_package_name,
    monkeypatch,
):
    from common_python_tasks.tasks import build_image

    monkeypatch.setenv("WORKDIR_PATH", "/app")
    monkeypatch.delenv("CONTAINER_BUILD_ARGS", raising=False)

    build_calls: list[list[str]] = []
    original = mock_run_command.side_effect

    def tracking(command, *args, **kwargs):
        if "docker" in command and "build" in command:
            build_calls.append(command)
        return original(command, *args, **kwargs)

    mock_run_command.side_effect = tracking

    build_image(build_args="WORKDIR_PATH=/custom")

    assert len(build_calls) == 1
    base_build_cmd = build_calls[0]
    assert any("WORKDIR_PATH=/custom" in str(a) for a in base_build_cmd)
    assert not any("WORKDIR_PATH=/app" in str(a) for a in base_build_cmd)


def test_fastapi_stack_up_passes_container_build_options(
    temp_project_dir,
    mock_load_data_file,
    mock_run_command,
):
    from common_python_tasks.tasks import fastapi_stack_up

    build_image_calls: list[dict[str, object]] = []

    def fake_build_image(*args, **kwargs):
        build_image_calls.append(kwargs)
        return ("version", "commit")

    with (
        patch("common_python_tasks.utils.build_image", new=fake_build_image),
        patch(
            "common_python_tasks.utils.load_container_env_tokens", return_value=["X=1"]
        ),
        patch(
            "common_python_tasks.utils.ensure_secrets_generated"
        ) as mock_secrets,  # noqa: F841
        patch(
            "common_python_tasks.utils.load_and_prepare_compose",
            return_value=([], [], [], {"API_PORT": "8080"}),
        ),
        patch("common_python_tasks.utils.run_docker_compose_command"),
    ):
        fastapi_stack_up(
            detach=True,
            build_args="FOO=bar",
            container_env="X=1",
            container_envfile="env1.env",
        )

    assert len(build_image_calls) == 1
    assert build_image_calls[0]["build_args"] == "FOO=bar"
    assert build_image_calls[0]["container_env"] == "X=1"
    assert build_image_calls[0]["container_envfile"] == "env1.env"


def test_build_image_fails_for_debug_without_dependency_group(
    temp_project_dir,
    mock_run_command,
    mock_load_data_file,
    mock_get_image_tag,
    mock_get_authors,
    mock_get_package_name,
):
    """Debug builds should fail fast when no debug dependency group exists."""
    from common_python_tasks.tasks import build_image

    with pytest.raises(SystemExit):
        build_image(debug=True)

    calls = [c.args[0] for c in mock_run_command.call_args_list]
    assert not any("docker" in cmd and "build" in cmd for cmd in calls)


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

    container_shell(no_echo_env=True)

    assert len(run_calls) == 1
    run_call = [str(part) for part in run_calls[0] if part is not None]

    assert "test-package:abc123" in " ".join(run_call)
    assert run_call[-2:] == [
        "-c",
        "$(command -v zsh || command -v fish || command -v ksh || command -v bash || command -v sh) || exit 127",
    ]


def test_container_shell_wraps_fallback_shell_with_env_dump(
    temp_project_dir,
    mock_run_command,
    mock_load_data_file,
    mock_get_package_name,
):
    """`container_shell` should compose a shell fallback command that survives `echo_env=True`."""
    from common_python_tasks.tasks import container_shell

    run_calls: list[list[str | None]] = []
    original = mock_run_command.side_effect

    def tracking(command, *args, **kwargs):
        if len(command) >= 3 and command[:3] == ["docker", "image", "ls"]:
            result = original(command, *args, **kwargs)
            result.stdout = "docker.io/test-package:abc123\n"
            return result
        if "docker" in command and "run" in command:
            run_calls.append(command)
        return original(command, *args, **kwargs)

    mock_run_command.side_effect = tracking

    container_shell(no_echo_env=False)

    assert len(run_calls) == 1
    run_call = [str(part) for part in run_calls[0] if part is not None]
    assert run_call[-2:] == [
        "-c",
        "echo '=== Container Environment Variables ===' && env && echo '===================================' && exec $(command -v zsh || command -v fish || command -v ksh || command -v bash || command -v sh) || exit 127",
    ]


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


class TestParseContainerDeps:
    """Tests for parse_container_deps env var handling."""

    def test_returns_none_when_unset(self, monkeypatch):
        from common_python_tasks.utils import parse_container_deps

        monkeypatch.delenv("CONTAINER_DEPS_CONTENT", raising=False)
        monkeypatch.delenv("CONTAINER_DEPS_FILE", raising=False)
        assert parse_container_deps() is None

    def test_returns_content_from_env(self, monkeypatch):
        from common_python_tasks.utils import parse_container_deps

        monkeypatch.setenv("CONTAINER_DEPS_CONTENT", "RUN apt-get install -y curl")
        assert parse_container_deps() == "RUN apt-get install -y curl"

    def test_returns_content_from_file(self, monkeypatch, tmp_path):
        from common_python_tasks.utils import parse_container_deps

        monkeypatch.delenv("CONTAINER_DEPS_CONTENT", raising=False)
        deps_file = tmp_path / "deps.Dockerfile"
        deps_file.write_text("RUN pip install boto3\n", encoding="utf-8")
        monkeypatch.setenv("CONTAINER_DEPS_FILE", str(deps_file))
        assert parse_container_deps() == "RUN pip install boto3"

    def test_returns_content_from_multiple_files(self, monkeypatch, tmp_path):
        from common_python_tasks.utils import parse_container_deps

        monkeypatch.delenv("CONTAINER_DEPS_CONTENT", raising=False)
        deps_file1 = tmp_path / "deps1.Dockerfile"
        deps_file1.write_text("RUN pip install boto3\n", encoding="utf-8")
        deps_file2 = tmp_path / "deps2.Dockerfile"
        deps_file2.write_text("RUN pip install requests\n", encoding="utf-8")
        monkeypatch.setenv(
            "CONTAINER_DEPS_FILE",
            f"{deps_file1}:{deps_file2}",
        )

        assert (
            parse_container_deps() == "RUN pip install boto3\nRUN pip install requests"
        )

    def test_file_source_returns_path_when_no_content(self, monkeypatch, tmp_path):
        from common_python_tasks.utils import parse_container_deps_source

        deps_file = tmp_path / "deps.Dockerfile"
        deps_file.write_text("FROM FILE\n", encoding="utf-8")
        monkeypatch.delenv("CONTAINER_DEPS_CONTENT", raising=False)
        monkeypatch.setenv("CONTAINER_DEPS_FILE", str(deps_file))

        dockerfile_path, content = parse_container_deps_source()
        assert dockerfile_path == deps_file
        assert content is None

    def test_file_source_returns_paths_when_multiple_files(self, monkeypatch, tmp_path):
        from common_python_tasks.utils import parse_container_deps_source

        deps_file1 = tmp_path / "deps1.Dockerfile"
        deps_file1.write_text("FROM FILE1\n", encoding="utf-8")
        deps_file2 = tmp_path / "deps2.Dockerfile"
        deps_file2.write_text("FROM FILE2\n", encoding="utf-8")
        monkeypatch.delenv("CONTAINER_DEPS_CONTENT", raising=False)
        monkeypatch.setenv(
            "CONTAINER_DEPS_FILE",
            f"{deps_file1}:{deps_file2}",
        )

        dockerfile_paths, content = parse_container_deps_source()
        assert dockerfile_paths == [deps_file1, deps_file2]
        assert content is None

    def test_content_overrides_file_source(self, monkeypatch, tmp_path):
        from common_python_tasks.utils import parse_container_deps_source

        deps_file = tmp_path / "deps.Dockerfile"
        deps_file.write_text("FROM FILE\n", encoding="utf-8")
        monkeypatch.setenv("CONTAINER_DEPS_CONTENT", "FROM ENV")
        monkeypatch.setenv("CONTAINER_DEPS_FILE", str(deps_file))

        dockerfile_path, content = parse_container_deps_source()
        assert dockerfile_path is None
        assert content == "FROM ENV"

    def test_file_missing_raises(self, monkeypatch):
        from common_python_tasks.utils import parse_container_deps

        monkeypatch.delenv("CONTAINER_DEPS_CONTENT", raising=False)
        monkeypatch.setenv("CONTAINER_DEPS_FILE", "/nonexistent/deps.Dockerfile")
        with pytest.raises(SystemExit):
            parse_container_deps()

    def test_empty_content_returns_none(self, monkeypatch):
        from common_python_tasks.utils import parse_container_deps

        monkeypatch.setenv("CONTAINER_DEPS_CONTENT", "   ")
        monkeypatch.delenv("CONTAINER_DEPS_FILE", raising=False)
        assert parse_container_deps() is None


class TestParseContainerDepsMappings:
    """Tests for parse_container_deps_mappings env var handling."""

    def test_returns_none_when_unset(self, monkeypatch):
        from common_python_tasks.utils import parse_container_deps_mappings

        monkeypatch.delenv("CONTAINER_DEPS_MAPPINGS", raising=False)
        assert parse_container_deps_mappings() is None

    def test_parses_simple_mappings(self, monkeypatch):
        from common_python_tasks.utils import parse_container_deps_mappings

        monkeypatch.setenv(
            "CONTAINER_DEPS_MAPPINGS",
            "dep1:/opt/dep1 dep2:/usr/local/bin/dep2",
        )
        assert parse_container_deps_mappings() == {
            "dep1": "/opt/dep1",
            "dep2": "/usr/local/bin/dep2",
        }

    def test_parses_quoted_paths(self, monkeypatch):
        from common_python_tasks.utils import parse_container_deps_mappings

        monkeypatch.setenv(
            "CONTAINER_DEPS_MAPPINGS",
            "dep1:'/opt/dep one' dep2:\"/usr/local/bin/dep two\"",
        )
        assert parse_container_deps_mappings() == {
            "dep1": "/opt/dep one",
            "dep2": "/usr/local/bin/dep two",
        }

    def test_invalid_token_raises(self, monkeypatch):
        from common_python_tasks.utils import parse_container_deps_mappings

        monkeypatch.setenv("CONTAINER_DEPS_MAPPINGS", "invalid-token")
        with pytest.raises(SystemExit):
            parse_container_deps_mappings()

    def test_duplicate_name_raises(self, monkeypatch):
        from common_python_tasks.utils import parse_container_deps_mappings

        monkeypatch.setenv(
            "CONTAINER_DEPS_MAPPINGS",
            "dep1:/opt/dep1 dep1:/opt/dep2",
        )
        with pytest.raises(SystemExit):
            parse_container_deps_mappings()


class TestRenderDepsMoveScript:
    """Tests for generating the dependency move script."""

    def test_script_contains_expected_move_logic(self):
        from common_python_tasks.utils import render_container_deps_move_script

        script = render_container_deps_move_script(
            {"dep1": "/opt/dep1", "dep2": "/usr/local/bin/dep2"}
        )
        assert "shutil.move" in script
        assert 'source_root = pathlib.Path("/tmp/deps")' in script
        assert "'dep1': '/opt/dep1'" in script


class TestBuildDepsImage:
    """Tests for build_deps_image building and tagging flow."""

    def test_builds_deps_image_and_returns_tag(
        self,
        mock_run_command,
        mock_load_data_file,
        mock_get_package_name,
    ):
        from common_python_tasks.utils import build_deps_image

        tag = build_deps_image("RUN apt-get install -y curl", single_arch=True)
        assert tag.startswith("test-package-deps:deps-")
        # Verify docker build was called
        docker_calls = [
            c
            for c in mock_run_command.call_args_list
            if c[0][0][0] == "docker" and c[0][0][1] == "build"
        ]
        assert len(docker_calls) == 1

    def test_builds_deps_image_from_dockerfile_path(
        self,
        tmp_path,
        mock_run_command,
        mock_load_data_file,
        mock_get_package_name,
    ):
        from common_python_tasks.utils import build_deps_image

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
        from common_python_tasks.utils import build_deps_image

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
        from common_python_tasks.utils import build_deps_image

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
        from common_python_tasks.utils import build_deps_image

        tag1 = build_deps_image("RUN apt-get install -y curl", single_arch=True)
        tag2 = build_deps_image("RUN apt-get install -y wget", single_arch=True)
        assert tag1 != tag2

    def test_same_content_gives_same_tag(
        self,
        mock_run_command,
        mock_load_data_file,
        mock_get_package_name,
    ):
        from common_python_tasks.utils import build_deps_image

        content = "RUN apt-get install -y jq"
        tag1 = build_deps_image(content, single_arch=True)
        tag2 = build_deps_image(content, single_arch=True)
        assert tag1 == tag2


class TestBuildImageWithDeps:
    """Tests for the build_image task integrating the deps image path."""

    def test_deps_image_built_when_env_set(
        self,
        monkeypatch,
        temp_project_dir,
        mock_run_command,
        mock_load_data_file,
        mock_get_image_tag,
        mock_get_authors,
        mock_get_package_name,
    ):
        """When CONTAINER_DEPS_CONTENT is set, deps image is built first."""
        from common_python_tasks.tasks import build_image

        monkeypatch.setenv("CONTAINER_DEPS_CONTENT", "RUN apt-get install -y curl")

        build_image(single_arch=True)

        docker_calls = [
            c
            for c in mock_run_command.call_args_list
            if c[0][0][0] == "docker" and c[0][0][1] == "build"
        ]
        # Two builds: deps image + main image
        assert len(docker_calls) == 2
        deps_call = docker_calls[0]
        main_call = docker_calls[1]
        deps_cmd = " ".join(str(x) for x in deps_call[0][0] if x is not None)
        main_cmd = " ".join(str(x) for x in main_call[0][0] if x is not None)
        assert "test-package-deps:deps-" in deps_cmd
        assert "DEPS_IMAGE" in main_cmd

    def test_renders_container_deps_move_script_when_mappings_set(
        self,
        monkeypatch,
        temp_project_dir,
        mock_run_command,
        mock_load_data_file,
        mock_get_image_tag,
        mock_get_authors,
        mock_get_package_name,
    ):
        from common_python_tasks.tasks import build_image

        captured: dict[str, str] = {}
        original_side_effect = mock_run_command.side_effect

        def tracking(command, *args, **kwargs):
            result = original_side_effect(command, *args, **kwargs)
            if isinstance(command, list) and len(command) >= 4:
                cmd = [str(c) for c in command if c is not None]
                if cmd[:2] == ["docker", "build"] and "-f" in cmd:
                    dockerfile_path = cmd[cmd.index("-f") + 1]
                    try:
                        captured["content"] = Path(dockerfile_path).read_text(
                            encoding="utf-8"
                        )
                    except FileNotFoundError:
                        captured["content"] = ""
            return result

        original_load_data_file = mock_load_data_file.side_effect

        def load_data_file_side_effect(
            filename, type_identifier="generic", fatal_on_missing=True
        ):
            if filename == "Dockerfile.j2":
                return (
                    "/fake/path/Dockerfile.j2",
                    "FROM python:3.11\n{% if DEPS_IMAGE %}\nARG DEPS_IMAGE\nCOPY --from={{ DEPS_IMAGE }} /tmp/deps /tmp/deps\n{% endif %}\n{% if CONTAINER_DEPS_MOVE_SCRIPT %}\nRUN set -eux; \\\n    cat >/tmp/container-deps-move-script <<'SCRIPT' && \\\n    chmod +x /tmp/container-deps-move-script && \\\n    /tmp/container-deps-move-script\n{{ CONTAINER_DEPS_MOVE_SCRIPT }}\nSCRIPT\n{% endif %}\n",
                )
            return original_load_data_file(filename, type_identifier, fatal_on_missing)

        mock_load_data_file.side_effect = load_data_file_side_effect
        monkeypatch.setenv("CONTAINER_DEPS_CONTENT", "RUN apt-get install -y curl")
        monkeypatch.setenv(
            "CONTAINER_DEPS_MAPPINGS",
            "dep1:/opt/dep1 dep2:/usr/local/bin/dep2",
        )
        mock_run_command.side_effect = tracking

        build_image(single_arch=True)

        assert "cat >/tmp/container-deps-move-script" in captured.get("content", "")
        assert "shutil.move" in captured.get("content", "")
        assert "'dep1': '/opt/dep1'" in captured.get("content", "")

    def test_uses_container_deps_move_script_from_env(
        self,
        monkeypatch,
        temp_project_dir,
        mock_run_command,
        mock_load_data_file,
        mock_get_image_tag,
        mock_get_authors,
        mock_get_package_name,
    ):
        from common_python_tasks.tasks import build_image

        captured: dict[str, str] = {}
        original_side_effect = mock_run_command.side_effect

        def tracking(command, *args, **kwargs):
            result = original_side_effect(command, *args, **kwargs)
            if isinstance(command, list) and len(command) >= 4:
                cmd = [str(c) for c in command if c is not None]
                if cmd[:2] == ["docker", "build"] and "-f" in cmd:
                    dockerfile_path = cmd[cmd.index("-f") + 1]
                    try:
                        captured["content"] = Path(dockerfile_path).read_text(
                            encoding="utf-8"
                        )
                    except FileNotFoundError:
                        captured["content"] = ""
            return result

        original_load_data_file = mock_load_data_file.side_effect

        def load_data_file_side_effect(
            filename, type_identifier="generic", fatal_on_missing=True
        ):
            if filename == "Dockerfile.j2":
                return (
                    "/fake/path/Dockerfile.j2",
                    "FROM python:3.11\n{% if DEPS_IMAGE %}\nARG DEPS_IMAGE\nCOPY --from={{ DEPS_IMAGE }} /tmp/deps /tmp/deps\n{% endif %}\n{% if CONTAINER_DEPS_MOVE_SCRIPT %}\nRUN set -eux; \\\n    cat >/tmp/container-deps-move-script <<'SCRIPT' && \\\n    chmod +x /tmp/container-deps-move-script && \\\n    /tmp/container-deps-move-script\n{{ CONTAINER_DEPS_MOVE_SCRIPT }}\nSCRIPT\n{% endif %}\n",
                )
            return original_load_data_file(filename, type_identifier, fatal_on_missing)

        mock_load_data_file.side_effect = load_data_file_side_effect
        mock_run_command.side_effect = tracking
        monkeypatch.setenv("CONTAINER_DEPS_CONTENT", "RUN apt-get install -y curl")
        monkeypatch.setenv(
            "CONTAINER_DEPS_MOVE_SCRIPT",
            "print('custom-move')",
        )

        build_image(single_arch=True)

        assert "print('custom-move')" in captured.get("content", "")
        assert "shutil.move" not in captured.get("content", "")
        assert "chmod +x /tmp/container-deps-move-script" in captured.get("content", "")

    def test_uses_container_deps_move_script_path(
        self,
        monkeypatch,
        temp_project_dir,
        mock_run_command,
        mock_load_data_file,
        mock_get_image_tag,
        mock_get_authors,
        mock_get_package_name,
    ):
        from common_python_tasks.tasks import build_image

        script_path = temp_project_dir / "move-deps.sh"
        script_path.write_text(
            "#!/usr/bin/env sh\necho moving deps >/tmp/deps/marker\n",
            encoding="utf-8",
        )

        captured: dict[str, str] = {}
        original_side_effect = mock_run_command.side_effect

        def tracking(command, *args, **kwargs):
            result = original_side_effect(command, *args, **kwargs)
            if isinstance(command, list) and len(command) >= 4:
                cmd = [str(c) for c in command if c is not None]
                if cmd[:2] == ["docker", "build"] and "-f" in cmd:
                    dockerfile_path = cmd[cmd.index("-f") + 1]
                    try:
                        captured["content"] = Path(dockerfile_path).read_text(
                            encoding="utf-8"
                        )
                    except FileNotFoundError:
                        captured["content"] = ""
            return result

        original_load_data_file = mock_load_data_file.side_effect

        def load_data_file_side_effect(
            filename, type_identifier="generic", fatal_on_missing=True
        ):
            if filename == "Dockerfile.j2":
                return (
                    "/fake/path/Dockerfile.j2",
                    "FROM python:3.11\n{% if DEPS_IMAGE %}\nARG DEPS_IMAGE\nCOPY --from={{ DEPS_IMAGE }} /tmp/deps /tmp/deps\n{% endif %}\n{% if CONTAINER_DEPS_MOVE_SCRIPT %}\nRUN set -eux; \\\n    cat >/tmp/container-deps-move-script <<'SCRIPT' && \\\n    chmod +x /tmp/container-deps-move-script && \\\n    /tmp/container-deps-move-script\n{{ CONTAINER_DEPS_MOVE_SCRIPT }}\nSCRIPT\n{% endif %}\n",
                )
            return original_load_data_file(filename, type_identifier, fatal_on_missing)

        mock_load_data_file.side_effect = load_data_file_side_effect
        mock_run_command.side_effect = tracking
        monkeypatch.setenv("CONTAINER_DEPS_CONTENT", "RUN apt-get install -y curl")
        monkeypatch.setenv("CONTAINER_DEPS_MOVE_SCRIPT_PATH", str(script_path))
        monkeypatch.setenv("CONTAINER_DEPS_MOVE_SCRIPT", "print('ignored')")

        build_image(single_arch=True)

        assert "#!/usr/bin/env sh" in captured.get("content", "")
        assert "chmod +x /tmp/container-deps-move-script" in captured.get("content", "")
        assert "echo moving deps" in captured.get("content", "")

    def test_container_deps_move_script_env_overrides_mappings(
        self,
        monkeypatch,
        temp_project_dir,
        mock_run_command,
        mock_load_data_file,
        mock_get_image_tag,
        mock_get_authors,
        mock_get_package_name,
    ):
        from common_python_tasks.tasks import build_image

        captured: dict[str, str] = {}
        original_side_effect = mock_run_command.side_effect

        def tracking(command, *args, **kwargs):
            result = original_side_effect(command, *args, **kwargs)
            if isinstance(command, list) and len(command) >= 4:
                cmd = [str(c) for c in command if c is not None]
                if cmd[:2] == ["docker", "build"] and "-f" in cmd:
                    dockerfile_path = cmd[cmd.index("-f") + 1]
                    try:
                        captured["content"] = Path(dockerfile_path).read_text(
                            encoding="utf-8"
                        )
                    except FileNotFoundError:
                        captured["content"] = ""
            return result

        original_load_data_file = mock_load_data_file.side_effect

        def load_data_file_side_effect(
            filename, type_identifier="generic", fatal_on_missing=True
        ):
            if filename == "Dockerfile.j2":
                return (
                    "/fake/path/Dockerfile.j2",
                    "FROM python:3.11\n{% if DEPS_IMAGE %}\nARG DEPS_IMAGE\nCOPY --from={{ DEPS_IMAGE }} /tmp/deps /tmp/deps\n{% endif %}\n{% if CONTAINER_DEPS_MOVE_SCRIPT %}\nRUN set -eux; \\\n    cat >/tmp/container-deps-move-script <<'SCRIPT' && \\\n    chmod +x /tmp/container-deps-move-script && \\\n    /tmp/container-deps-move-script\n{{ CONTAINER_DEPS_MOVE_SCRIPT }}\nSCRIPT\n{% endif %}\n",
                )
            return original_load_data_file(filename, type_identifier, fatal_on_missing)

        mock_load_data_file.side_effect = load_data_file_side_effect
        mock_run_command.side_effect = tracking
        monkeypatch.setenv("CONTAINER_DEPS_CONTENT", "RUN apt-get install -y curl")
        monkeypatch.setenv(
            "CONTAINER_DEPS_MOVE_SCRIPT",
            "print('custom-move')",
        )
        monkeypatch.setenv(
            "CONTAINER_DEPS_MAPPINGS",
            "dep1:/opt/dep1",
        )

        build_image(single_arch=True)

        assert "print('custom-move')" in captured.get("content", "")
        assert "'dep1'" not in captured.get("content", "")
        assert "chmod +x /tmp/container-deps-move-script" in captured.get("content", "")

    def test_logs_container_deps_move_script_in_debug_mode(
        self,
        monkeypatch,
        caplog,
        temp_project_dir,
        mock_run_command,
        mock_load_data_file,
        mock_get_image_tag,
        mock_get_authors,
        mock_get_package_name,
    ):
        from common_python_tasks.tasks import build_image

        original_load_data_file = mock_load_data_file.side_effect

        def load_data_file_side_effect(
            filename, type_identifier="generic", fatal_on_missing=True
        ):
            if filename == "Dockerfile.j2":
                return (
                    "/fake/path/Dockerfile.j2",
                    "FROM python:3.11\n{% if DEPS_IMAGE %}\nARG DEPS_IMAGE\nCOPY --from={{ DEPS_IMAGE }} /tmp/deps /tmp/deps\n{% endif %}\n{% if CONTAINER_DEPS_MOVE_SCRIPT %}\nRUN set -eux; \\\n    cat >/tmp/container-deps-move-script <<'SCRIPT' && \\\n    chmod +x /tmp/container-deps-move-script && \\\n    /tmp/container-deps-move-script\n{{ CONTAINER_DEPS_MOVE_SCRIPT }}\nSCRIPT\n{% endif %}\n",
                )
            return original_load_data_file(filename, type_identifier, fatal_on_missing)

        mock_load_data_file.side_effect = load_data_file_side_effect
        monkeypatch.setenv("CONTAINER_DEPS_CONTENT", "RUN apt-get install -y curl")
        monkeypatch.setenv(
            "CONTAINER_DEPS_MAPPINGS",
            "dep1:/opt/dep1 dep2:/usr/local/bin/dep2",
        )

        caplog.set_level(logging.DEBUG, logger="common_python_tasks")

        build_image(single_arch=True)

        assert any(
            "Rendered container deps move script" in record.message
            for record in caplog.records
        )
        assert any("shutil.move" in record.message for record in caplog.records)

    def test_renders_container_deps_move_script_with_external_deps_image(
        self,
        monkeypatch,
        temp_project_dir,
        mock_run_command,
        mock_load_data_file,
        mock_get_image_tag,
        mock_get_authors,
        mock_get_package_name,
    ):
        from common_python_tasks.tasks import build_image

        captured: dict[str, str] = {}
        original_side_effect = mock_run_command.side_effect

        def tracking(command, *args, **kwargs):
            result = original_side_effect(command, *args, **kwargs)
            if isinstance(command, list) and len(command) >= 4:
                cmd = [str(c) for c in command if c is not None]
                if cmd[:2] == ["docker", "build"] and "-f" in cmd:
                    dockerfile_path = cmd[cmd.index("-f") + 1]
                    try:
                        captured["content"] = Path(dockerfile_path).read_text(
                            encoding="utf-8"
                        )
                    except FileNotFoundError:
                        captured["content"] = ""
            return result

        original_load_data_file = mock_load_data_file.side_effect

        def load_data_file_side_effect(
            filename, type_identifier="generic", fatal_on_missing=True
        ):
            if filename == "Dockerfile.j2":
                return (
                    "/fake/path/Dockerfile.j2",
                    "FROM python:3.11\n{% if DEPS_IMAGE %}\nARG DEPS_IMAGE\nCOPY --from={{ DEPS_IMAGE }} /tmp/deps /tmp/deps\n{% endif %}\n{% if CONTAINER_DEPS_MOVE_SCRIPT %}\nRUN set -eux; \\\n    cat >/tmp/container-deps-move-script <<'SCRIPT' && \\\n    chmod +x /tmp/container-deps-move-script && \\\n    /tmp/container-deps-move-script\n{{ CONTAINER_DEPS_MOVE_SCRIPT }}\nSCRIPT\n{% endif %}\n",
                )
            return original_load_data_file(filename, type_identifier, fatal_on_missing)

        mock_load_data_file.side_effect = load_data_file_side_effect
        monkeypatch.setenv(
            "CONTAINER_DEPS_MAPPINGS",
            "dep1:/opt/dep1 dep2:/usr/local/bin/dep2",
        )
        mock_run_command.side_effect = tracking

        build_image(single_arch=True, build_args="DEPS_IMAGE=custom/deps")

        assert "COPY --from=custom/deps /tmp/deps /tmp/deps" in captured.get(
            "content", ""
        )
        assert "cat >/tmp/container-deps-move-script" in captured.get("content", "")
        assert "'dep1': '/opt/dep1'" in captured.get("content", "")

    def test_no_deps_image_when_env_unset(
        self,
        monkeypatch,
        temp_project_dir,
        mock_run_command,
        mock_load_data_file,
        mock_get_image_tag,
        mock_get_authors,
        mock_get_package_name,
    ):
        """When no CONTAINER_DEPS_CONTENT, only one build occurs (no deps image)."""
        from common_python_tasks.tasks import build_image

        monkeypatch.delenv("CONTAINER_DEPS_CONTENT", raising=False)
        monkeypatch.delenv("CONTAINER_DEPS_FILE", raising=False)

        build_image(single_arch=True)

        docker_calls = [
            c
            for c in mock_run_command.call_args_list
            if c[0][0][0] == "docker" and c[0][0][1] == "build"
        ]
        assert len(docker_calls) == 1
