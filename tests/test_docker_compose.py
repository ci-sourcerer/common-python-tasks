from pathlib import Path

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
