from pathlib import Path
from typing import ClassVar
from unittest.mock import MagicMock, patch

from common_python_tasks.docker_compose import (
    get_compose_env,
    get_required_vars_for_files,
)


def test_get_compose_env_includes_workdir_path_default(monkeypatch):
    monkeypatch.delenv("WORKDIR_PATH", raising=False)

    env = get_compose_env()

    assert env["WORKDIR_PATH"] == "/workspace"


def test_get_compose_env_uses_workdir_path_from_env(monkeypatch):
    monkeypatch.setenv("WORKDIR_PATH", "/app")

    env = get_compose_env()

    assert env["WORKDIR_PATH"] == "/app"


def test_get_required_vars_for_files_includes_workdir_path_for_compose_db():
    vars_required = get_required_vars_for_files("fastapi", [Path("compose-db.yml")])

    assert "WORKDIR_PATH" in vars_required


def test_get_compose_type_returns_default_fastapi(monkeypatch):
    from common_python_tasks.docker_compose import get_compose_type

    monkeypatch.delenv("COMPOSE_TYPE", raising=False)

    result = get_compose_type()

    assert result == "fastapi"


def test_get_compose_type_returns_env_value(monkeypatch):
    from common_python_tasks.docker_compose import get_compose_type

    monkeypatch.setenv("COMPOSE_TYPE", "custom")

    result = get_compose_type()

    assert result == "custom"


def test_load_compose_files_uses_default_compose_type(monkeypatch):
    from common_python_tasks import docker_compose

    monkeypatch.delenv("COMPOSE_TYPE", raising=False)

    dummy_path = Path("compose-base.yml")
    with patch("common_python_tasks.docker_compose.render_file") as mock_render_file:
        mock_render_file.return_value = (dummy_path, False)

        results, temp_compose_files, temp_config_files = (
            docker_compose.load_compose_files()
        )

    assert results == [dummy_path]
    assert temp_compose_files == []
    assert temp_config_files == []
    mock_render_file.assert_called_once()
    assert mock_render_file.call_args.args[0] == "FASTAPI_COMPOSE_BASE"


def test_run_docker_compose_command_includes_env_files(monkeypatch, tmp_path):
    from common_python_tasks.docker_compose import run_docker_compose_command

    class DummyTasks:
        envfile: ClassVar = [Path(".env1"), Path(".env2")]

    called = []

    def fake_run_command(command, **kwargs):
        called.append(command)
        return MagicMock(returncode=0, stdout="")

    monkeypatch.setattr(
        "common_python_tasks.docker_compose.utils.run_command", fake_run_command
    )

    run_docker_compose_command(
        "up",
        compose_files=[tmp_path / "compose.yml"],
        compose_env={"A": "B"},
        tasks=DummyTasks(),
    )

    assert called
    assert "--env-file" in called[0]
    assert str(Path(".env1")) in called[0]
    assert str(Path(".env2")) in called[0]


def test_load_compose_files_supports_quoted_colon_delimited_paths(
    monkeypatch,
    tmp_path,
):
    from common_python_tasks.docker_compose import load_compose_files

    compose_a = tmp_path / "compose-base.yml"
    compose_a.write_text("", encoding="utf-8")
    compose_b = tmp_path / "compose with spaces.yml"
    compose_b.write_text("", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "COMPOSE_FILE",
        '"compose-base.yml":"compose with spaces.yml"',
    )

    results, _, _ = load_compose_files()

    assert results == [Path("compose-base.yml"), Path("compose with spaces.yml")]


def test_read_dotenv_parses_simple_env_file(tmp_path):
    from common_python_tasks.docker_compose import read_dotenv

    dotenv = tmp_path / ".env"
    dotenv.write_text("API_PORT=8000\nDEBUG=true\n", encoding="utf-8")

    result = read_dotenv(dotenv)

    assert result["API_PORT"] == "8000"
    assert result["DEBUG"] == "true"


def test_ensure_secrets_generated_creates_keys(tmp_path, monkeypatch):
    from common_python_tasks.docker_compose import ensure_secrets_generated

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("DB_PASS", raising=False)

    ensure_secrets_generated()

    dotenv = tmp_path / ".env"
    content = dotenv.read_text(encoding="utf-8")
    assert "SECRET_KEY=" in content
    assert "DB_PASS=" in content


def test_ensure_alembic_config_reuses_identifiable_generated_file(
    tmp_path, monkeypatch
):
    from common_python_tasks.docker_compose import (
        cleanup_temp_files,
        ensure_alembic_config,
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "common_python_tasks.docker_compose.utils.load_data_file",
        lambda *args, **kwargs: (
            Path("alembic.ini.j2"),
            "package = {{ package_name }}",
        ),
    )
    monkeypatch.setattr(
        "common_python_tasks.docker_compose.utils.get_package_name",
        lambda **kwargs: "example_package",
    )

    config_path, should_cleanup = ensure_alembic_config("fastapi")

    assert config_path == Path(".fastapi.alembic.ini.common-python-tasks")
    assert should_cleanup
    assert config_path.read_text(encoding="utf-8") == "package = example_package"
    assert ensure_alembic_config("fastapi") == (config_path, True)

    cleanup_temp_files([config_path])
    assert not config_path.exists()
