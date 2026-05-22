import logging
from pathlib import Path

import pytest


def test_build_with_multiple_extensions(
    temp_project_dir,
    mock_run_command,
    mock_load_data_file,
    mock_get_image_tag,
    mock_get_authors,
    mock_get_package_name,
    monkeypatch,
):
    """Building with multiple extension Dockerfiles should inject both fragments into one build."""
    from common_python_tasks.tasks import build_image

    ext1 = temp_project_dir / "Dockerfile.ext1"
    ext1.write_text("# ext1\nRUN echo ext1\n", encoding="utf-8")
    ext2 = temp_project_dir / "Dockerfile.ext2"
    ext2.write_text("# ext2\nRUN echo ext2\n", encoding="utf-8")

    monkeypatch.setenv("CONTAINER_EXTENSION_FILES", f"{ext1}:{ext2}")
    monkeypatch.delenv("CONTAINER_EXTENSIONS", raising=False)

    original_load_data_file = mock_load_data_file.side_effect

    def load_data_file_with_extensions(
        filename, type_identifier="generic", fatal_on_missing=True
    ):
        if filename == "Dockerfile.j2":
            return (
                "/fake/path/Dockerfile.j2",
                "FROM python:3.11\n" "{{ EXTENSION_CONTENT|default('') }}\n",
            )
        return original_load_data_file(filename, type_identifier, fatal_on_missing)

    mock_load_data_file.side_effect = load_data_file_with_extensions

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
    assert "RUN echo ext1" in captured_dockerfile["content"]
    assert "RUN echo ext2" in captured_dockerfile["content"]
    assert captured_dockerfile["content"].index("RUN echo ext1") < captured_dockerfile[
        "content"
    ].index("RUN echo ext2")


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

    build_image(container_env=["SOURCE=cli"])

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

    build_image(container_envfile=[str(envfile_path)])

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

    build_image(container_envfile=[str(envfile_path_1), str(envfile_path_2)])

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
        "common_python_tasks.project.get_installed_requirement_version",
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

    build_image(build_args=["POETRY_VERSION=9.9.9"])

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

    build_image(build_args=["WORKDIR_PATH=/custom"])

    assert len(build_calls) == 1
    base_build_cmd = build_calls[0]
    assert any("WORKDIR_PATH=/custom" in str(a) for a in base_build_cmd)
    assert not any("WORKDIR_PATH=/app" in str(a) for a in base_build_cmd)


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

        build_image(single_arch=True, build_args=["DEPS_IMAGE=custom/deps"])

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
