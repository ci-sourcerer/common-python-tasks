from common_python_tasks.env import inject_auto_build_args_from_env


def test_inject_auto_build_args_from_env_adds_value(monkeypatch):
    monkeypatch.setenv("WORKDIR_PATH", "/app")

    result = inject_auto_build_args_from_env({})

    assert result["WORKDIR_PATH"] == "/app"


def test_inject_auto_build_args_from_env_preserves_explicit_value(monkeypatch):
    monkeypatch.setenv("WORKDIR_PATH", "/app")

    result = inject_auto_build_args_from_env({"WORKDIR_PATH": "/custom"})

    assert result["WORKDIR_PATH"] == "/custom"
