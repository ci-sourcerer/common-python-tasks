from common_python_tasks.env import (
    inject_auto_build_args_from_env,
    load_container_env_tokens,
    parse_container_env_tokens,
)


def test_inject_auto_build_args_from_env_adds_value(monkeypatch):
    monkeypatch.setenv("WORKDIR_PATH", "/app")

    result = inject_auto_build_args_from_env({})

    assert result["WORKDIR_PATH"] == "/app"


def test_inject_auto_build_args_from_env_preserves_explicit_value(monkeypatch):
    monkeypatch.setenv("WORKDIR_PATH", "/app")

    result = inject_auto_build_args_from_env({"WORKDIR_PATH": "/custom"})

    assert result["WORKDIR_PATH"] == "/custom"


def test_parse_container_env_tokens_accepts_list_values():
    result = parse_container_env_tokens(["A=one", "B=two"])

    assert result == ["A=one", "B=two"]


def test_load_container_env_tokens_accepts_list_container_envfile(tmp_path):
    envfile = tmp_path / "container.env"
    envfile.write_text("A=one", encoding="utf-8")

    result = load_container_env_tokens(container_envfile=[str(envfile)])

    assert result == ["A=one"]


def test_load_container_env_tokens_supports_colon_delimited_envfile_string(tmp_path):
    first_envfile = tmp_path / "first.env"
    second_envfile = tmp_path / "second.env"
    first_envfile.write_text("A=one", encoding="utf-8")
    second_envfile.write_text("B=two", encoding="utf-8")

    result = load_container_env_tokens(
        container_envfile=f"{first_envfile}:{second_envfile}"
    )

    assert result == ["A=one", "B=two"]
