import os
import subprocess
import time
import uuid

import pytest

from common_python_tasks.env import (
    parse_container_extensions,
    resolve_extension_build_context,
    resolve_extension_content,
)
from common_python_tasks.utils import load_data_file, render_template_text


def _extension():
    return load_data_file(
        "docker-in-docker/Dockerfile", type_identifier="dockerfile_extensions"
    )[1]


def _extension_context():
    return load_data_file(
        "docker-in-docker/Dockerfile", type_identifier="dockerfile_extensions"
    )[0].parent


def test_dind_bundle_resolves_without_project_files(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CONTAINER_EXTENSION_FILES", raising=False)
    monkeypatch.setenv(
        "CONTAINER_EXTENSIONS", 'docker-in-docker="5:29.8.1-1~debian.12~bookworm"'
    )
    assert resolve_extension_content(parse_container_extensions()[0]) == _extension()
    assert parse_container_extensions()[0]["args"] == "5:29.8.1-1~debian.12~bookworm"
    assert resolve_extension_build_context(parse_container_extensions()[0]) == (
        "cpt-extension-docker-in-docker",
        _extension_context(),
    )


def test_dind_scripts_are_packaged_as_separate_assets():
    extension = _extension()
    assert "<<'INSTALL_DIND'" not in extension
    assert "<<'DIND_ENTRYPOINT'" not in extension
    assert "COPY --from=cpt-extension-docker-in-docker" in extension
    assert (_extension_context() / "install.sh").is_file()
    assert (_extension_context() / "supervisor.sh").is_file()


def test_cgroup_migration_suppresses_expected_write_races():
    supervisor = (_extension_context() / "supervisor.sh").read_text(encoding="utf-8")
    assert "/sys/fs/cgroup/cpt-init/cgroup.procs >/dev/null 2>&1 || true" in supervisor
    assert "/sys/fs/cgroup/cgroup.subtree_control >/dev/null 2>&1" in supervisor


def test_dind_redirects_daemon_logs_to_a_dedicated_file():
    supervisor = (_extension_context() / "supervisor.sh").read_text(encoding="utf-8")
    assert (
        "DIND_DOCKER_LOG_PATH=${DIND_DOCKER_LOG_PATH:-/var/log/docker.log}"
        in supervisor
    )
    assert '>>"$DIND_DOCKER_LOG_PATH" 2>&1' in supervisor


@pytest.mark.parametrize("debug", [False, True])
@pytest.mark.parametrize("extension", ["", "ARG RUNTIME_USER=root\nUSER root"])
def test_derived_stages_preserve_runtime_user(debug, extension):
    dockerfile = render_template_text(
        load_data_file("Dockerfile.j2")[1],
        {"EXTENSION_CONTENT": extension, "HAS_DEBUG_DEPS": debug},
    )
    runtime, final = dockerfile.split("FROM runtime AS final")
    assert "ARG RUNTIME_USER=py" in runtime
    assert "USER ${RUNTIME_USER}" in final
    assert "USER py" not in dockerfile
    if debug:
        assert "USER ${RUNTIME_USER}" in runtime.split("FROM runtime AS debug")[1]


def test_application_entrypoint_executes_selected_command():
    assert "exec python" in render_template_text(load_data_file("Dockerfile.j2")[1], {})


def test_dind_wraps_the_generated_entrypoint_without_redeclaring_it():
    extension = _extension()
    assert "mv /pkg/entrypoint.sh /pkg/application-entrypoint.sh" in extension
    assert "/pkg/application-entrypoint.sh" in extension
    assert "\nENTRYPOINT " not in extension


def _docker(*args, check=True, timeout=180):
    return subprocess.run(
        ["docker", *args],
        shell=False,
        check=check,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@pytest.fixture(scope="module")
def dind_image(tmp_path_factory):
    """Build the generated application image for opt-in privileged tests.

    Args:
        tmp_path_factory: Factory for isolated build contexts.

    Yields:
        The temporary Docker image tag.
    """
    if os.environ.get("CPT_DIND_INTEGRATION") != "1":
        pytest.skip("Set CPT_DIND_INTEGRATION=1 to build and run privileged DinD tests")
    context = tmp_path_factory.mktemp("dind-image")
    (context / "pyproject.toml").write_text(
        '[project]\nname = "dind-smoke"\nversion = "0.0.0"\n'
        '[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "setuptools.build_meta"\n',
        encoding="utf-8",
    )
    (context / "dind_smoke").mkdir()
    (context / "dind_smoke" / "__init__.py").touch()
    (context / "Dockerfile").write_text(
        render_template_text(
            load_data_file("Dockerfile.j2")[1], {"EXTENSION_CONTENT": _extension()}
        ),
        encoding="utf-8",
    )
    image = f"cpt-dind-test:{uuid.uuid4().hex}"
    try:
        result = _docker(
            "build",
            "--build-arg",
            "PYTHON_VERSION=3.14",
            "--build-arg",
            "PYTHON_VARIANT=slim-bookworm",
            "--build-arg",
            "PACKAGE_NAME=dind_smoke",
            "--build-context",
            f"cpt-extension-docker-in-docker={_extension_context()}",
            "--tag",
            image,
            str(context),
            check=False,
            timeout=900,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        yield image
    finally:
        _docker("image", "rm", image, check=False)


@pytest.fixture
def dind_container(dind_image):
    """Reserve a container name and clean up its volumes after the test.

    Args:
        dind_image: Image fixture whose lifetime includes container cleanup.

    Yields:
        A unique container name.
    """
    name = f"cpt-dind-test-{uuid.uuid4().hex}"
    try:
        yield name
    finally:
        _docker("rm", "--force", "--volumes", name, check=False)


def _run_app(image, name, code, *options):
    return _docker("run", "--name", name, *options, image, "-c", code, check=False)


def test_dind_runs_nested_workload_as_py(dind_image, dind_container):
    result = _run_app(
        dind_image,
        dind_container,
        "import os, subprocess; assert os.getuid() == 1000; "
        "subprocess.run(['docker', 'run', '--rm', 'alpine:3.22', "
        "'sh', '-c', 'echo nested-ok'], check=True); "
        "subprocess.run(['docker', 'buildx', 'version'], check=True); "
        "subprocess.run(['docker', 'compose', 'version'], check=True)",
        "--privileged",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "nested-ok" in result.stdout
    assert "write error: Device or resource busy" not in result.stderr


def test_dind_preserves_application_exit_code(dind_image, dind_container):
    result = _run_app(
        dind_image, dind_container, "import sys; sys.exit(42)", "--privileged"
    )
    assert result.returncode == 42, result.stdout + result.stderr


@pytest.mark.parametrize("options", [[], ["--privileged", "--user", "py"]])
def test_dind_rejects_missing_privileges(dind_image, dind_container, options):
    result = _run_app(dind_image, dind_container, "print('app-started')", *options)
    assert result.returncode != 0
    assert "--privileged" in result.stderr
    assert "app-started" not in result.stdout


def test_dind_daemon_failure_prevents_application_start(
    dind_image, dind_container, tmp_path
):
    (tmp_path / "daemon.json").write_text('{"not-a-docker-option": true}')
    result = _run_app(
        dind_image,
        dind_container,
        "print('app-started')",
        "--privileged",
        "--volume",
        f"{tmp_path / 'daemon.json'}:/etc/docker/daemon.json:ro",
    )
    assert result.returncode != 0
    assert "daemon exited during startup" in result.stderr
    assert "app-started" not in result.stdout


def test_dind_startup_timeout_prevents_application_start(
    dind_image, dind_container, tmp_path
):
    (tmp_path / "dockerd").write_text("#!/bin/sh\nexec sleep 300\n")
    (tmp_path / "dockerd").chmod(0o755)
    result = _run_app(
        dind_image,
        dind_container,
        "print('app-started')",
        "--privileged",
        "--env",
        "DIND_STARTUP_TIMEOUT=1",
        "--volume",
        f"{tmp_path / 'dockerd'}:/usr/bin/dockerd:ro",
    )
    assert result.returncode != 0
    assert "timed out waiting for the daemon" in result.stderr
    assert "app-started" not in result.stdout


def test_dind_rejects_unsupported_distribution(dind_image, tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM alpine:3.22\n" + _extension())
    result = _docker(
        "build",
        "--build-context",
        f"cpt-extension-docker-in-docker={_extension_context()}",
        str(tmp_path),
        check=False,
    )
    assert result.returncode != 0
    assert "requires Debian Bookworm" in result.stderr


def _wait_for_output(name, expected):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if expected in _docker("logs", name).stdout:
            return
        time.sleep(0.2)
    pytest.fail(f"Container never produced {expected}: {_docker('logs', name).stderr}")


def test_dind_forwards_stop_and_can_restart(dind_image, dind_container):
    _docker(
        "run",
        "--detach",
        "--privileged",
        "--name",
        dind_container,
        dind_image,
        "-c",
        "import signal, sys, time; "
        "signal.signal(signal.SIGTERM, lambda *_: "
        "(print('app-stopped', flush=True), sys.exit(0))); "
        "print('app-ready', flush=True); time.sleep(300)",
    )
    _wait_for_output(dind_container, "app-ready")
    _docker("stop", "--time", "20", dind_container)
    assert "app-stopped" in _docker("logs", dind_container).stdout
    assert (
        _docker(
            "inspect", "--format", "{{.State.ExitCode}}", dind_container
        ).stdout.strip()
        == "143"
    )
    _docker("start", dind_container)
    _wait_for_output(dind_container, "app-ready\napp-stopped\napp-ready")
    _docker("exec", "--user", "py", dind_container, "docker", "info")


def test_dind_stops_application_when_daemon_exits(dind_image, dind_container):
    _docker(
        "run",
        "--detach",
        "--privileged",
        "--name",
        dind_container,
        dind_image,
        "-c",
        "import time; print('app-ready'); time.sleep(300)",
    )
    _wait_for_output(dind_container, "app-ready")
    _docker(
        "exec", dind_container, "sh", "-c", 'kill -TERM "$(cat /var/run/docker.pid)"'
    )
    assert _docker("wait", dind_container, timeout=30).stdout.strip() == "1"
    assert (
        "daemon exited while the app was running"
        in _docker("logs", dind_container).stderr
    )
