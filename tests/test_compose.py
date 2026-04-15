from pathlib import Path

from common_python_tasks.compose import get_compose_env, get_required_vars_for_files


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
