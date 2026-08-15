import pytest

from common_python_tasks.env import (
    inject_auto_build_args_from_env,
    load_container_env_tokens,
    parse_container_env_tokens,
    resolve_container_docker_build_args,
    resolve_container_dockerfile_hook_path,
    split_colon_delimited_values,
)


@pytest.mark.parametrize(
    ("env_var", "env_value", "input_map", "expected"),
    [
        ("WORKDIR_PATH", "/app", {}, {"WORKDIR_PATH": "/app"}),
        (
            "WORKDIR_PATH",
            "/app",
            {"WORKDIR_PATH": "/custom"},
            {"WORKDIR_PATH": "/custom"},
        ),
    ],
)
def test_inject_auto_build_args_from_env(
    monkeypatch, env_var, env_value, input_map, expected
):
    monkeypatch.setenv(env_var, env_value)

    result = inject_auto_build_args_from_env(input_map)

    for key, value in expected.items():
        assert result[key] == value


def test_parse_container_env_tokens_accepts_list_values():
    result = parse_container_env_tokens(["A=one", "B=two"])

    assert result == ["A=one", "B=two"]


def test_split_colon_delimited_values_preserves_quoted_substrings():
    result = split_colon_delimited_values('path:"my path/with:colon":other')

    assert result == ["path", "my path/with:colon", "other"]


def test_split_colon_delimited_values_preserves_escaped_colons():
    result = split_colon_delimited_values(
        r"URL=https\://example.com\:8443/path:MODE=prod"
    )

    assert result == ["URL=https://example.com:8443/path", "MODE=prod"]


def test_resolve_container_docker_build_args_prefers_cli_values():
    result = resolve_container_docker_build_args(
        ("--secret", "id=pip_conf,env=PIP_CONF"),
        "--ssh ignored",
    )

    assert result == ["--secret", "id=pip_conf,env=PIP_CONF"]


def test_resolve_container_docker_build_args_uses_shell_tokenized_env_value():
    result = resolve_container_docker_build_args(
        (),
        '--secret "id=pip conf,src=/tmp/pip.conf" --add-host example:127.0.0.1',
    )

    assert result == [
        "--secret",
        "id=pip conf,src=/tmp/pip.conf",
        "--add-host",
        "example:127.0.0.1",
    ]


def test_resolve_container_docker_build_args_rejects_invalid_shell_quoting():
    with pytest.raises(SystemExit):
        resolve_container_docker_build_args((), '--label "unterminated')


def test_resolve_container_dockerfile_hook_path_validates_executable(tmp_path):
    hook_path = tmp_path / "mutate-dockerfile.sh"
    hook_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    hook_path.chmod(0o755)

    result = resolve_container_dockerfile_hook_path(str(hook_path), None)

    assert result == hook_path


def test_resolve_container_dockerfile_hook_path_rejects_non_executable(tmp_path):
    hook_path = tmp_path / "mutate-dockerfile.sh"
    hook_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    hook_path.chmod(0o644)

    with pytest.raises(SystemExit):
        resolve_container_dockerfile_hook_path(str(hook_path), None)


def test_parse_container_env_tokens_supports_whitespace_delimited_values():
    result = parse_container_env_tokens("A=one B='two with spaces'")

    assert result == ["A=one", "B=two with spaces"]


def test_parse_container_env_tokens_accepts_escaped_colons():
    result = parse_container_env_tokens(
        r"DATABASE_URL=postgresql\://user\:pass@db\:5432/app:MODE=prod"
    )

    assert result == [
        "DATABASE_URL=postgresql://user:pass@db:5432/app",
        "MODE=prod",
    ]


def test_parse_container_env_tokens_rejects_unescaped_colons():
    with pytest.raises(SystemExit):
        parse_container_env_tokens("DATABASE_URL=postgresql://db:5432/app:MODE=prod")


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


@pytest.mark.parametrize(
    ("dotenv_contents", "expected"),
    [
        ("KEY1=value1\nKEY2=value2\n", {"KEY1": "value1", "KEY2": "value2"}),
        (
            "# Comment\nKEY1=value1\n\n# Another comment\nKEY2=value2\n",
            {"KEY1": "value1", "KEY2": "value2"},
        ),
        ("KEY1=\"quoted\"\nKEY2='single'\n", {"KEY1": "quoted", "KEY2": "single"}),
    ],
)
def test_read_dotenv_parses_various_formats(tmp_path, dotenv_contents, expected):
    from common_python_tasks.docker_compose import read_dotenv

    dotenv = tmp_path / ".env"
    dotenv.write_text(dotenv_contents, encoding="utf-8")

    result = read_dotenv(dotenv)

    assert result == expected


def test_read_dotenv_returns_empty_dict_when_file_missing(tmp_path):
    from common_python_tasks.docker_compose import read_dotenv

    result = read_dotenv(tmp_path / "nonexistent.env")

    assert result == {}


def test_append_dotenv_creates_header_comment(tmp_path, monkeypatch):
    from common_python_tasks.docker_compose import append_dotenv

    monkeypatch.chdir(tmp_path)
    dotenv = tmp_path / ".env"
    dotenv.write_text("EXISTING=value\n", encoding="utf-8")

    append_dotenv(dotenv, {"NEW_KEY": "new_value"})

    content = dotenv.read_text(encoding="utf-8")
    assert "EXISTING=value" in content
    assert "NEW_KEY=new_value" in content
    assert "Auto-generated by common_python_tasks" in content


def test_get_or_generate_secret_returns_existing_env_var(monkeypatch):
    from common_python_tasks.docker_compose import get_or_generate_secret

    monkeypatch.setenv("TEST_SECRET", "existing-value")
    result = get_or_generate_secret("TEST_SECRET")

    assert result == "existing-value"


def test_get_or_generate_secret_generates_and_stores_new_secret(tmp_path, monkeypatch):
    from common_python_tasks.docker_compose import get_or_generate_secret

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NEW_SECRET", raising=False)

    result = get_or_generate_secret("NEW_SECRET", length_bytes=16)

    assert result is not None
    assert len(result) == 32  # hex encoded 16 bytes = 32 chars
    dotenv = tmp_path / ".env"
    assert f"NEW_SECRET={result}" in dotenv.read_text(encoding="utf-8")


def test_load_container_env_file_reads_existing_file(tmp_path):
    from common_python_tasks.env import load_container_env_file

    env_file = tmp_path / ".containerenv"
    env_file.write_text("KEY=value\n", encoding="utf-8")

    result = load_container_env_file(str(env_file))

    assert result == "KEY=value"


def test_load_container_env_file_returns_none_when_missing(tmp_path):
    from unittest.mock import patch

    from common_python_tasks.env import load_container_env_file

    with patch("common_python_tasks.utils.fatal", side_effect=SystemExit(1)):
        with pytest.raises(SystemExit):
            load_container_env_file(str(tmp_path / "missing.env"))


def test_load_container_env_file_returns_none_for_empty_file(tmp_path):
    from common_python_tasks.env import load_container_env_file

    env_file = tmp_path / ".containerenv"
    env_file.write_text("\n\n", encoding="utf-8")

    result = load_container_env_file(str(env_file))

    assert result is None


class TestParseContainerExtensions:
    """Tests for parse_container_extensions parameter parsing."""

    @pytest.mark.parametrize(
        ("extensions_value", "expected"),
        [
            (
                "some_ext",
                [
                    {
                        "id": "some_ext",
                        "bundle_name": "some_ext",
                        "args": None,
                    }
                ],
            ),
            (
                'some_ext="jq curl"',
                [
                    {
                        "id": "some_ext",
                        "bundle_name": "some_ext",
                        "args": "jq curl",
                    }
                ],
            ),
            (
                'some_ext="jq curl wget":plain_ext',
                [
                    {"id": "some_ext", "args": "jq curl wget"},
                    {"id": "plain_ext", "args": None},
                ],
            ),
            (
                "some_ext=",
                [{"id": "some_ext", "args": ""}],
            ),
        ],
    )
    def test_parse_container_extensions(self, monkeypatch, extensions_value, expected):
        from common_python_tasks.env import parse_container_extensions

        monkeypatch.delenv("CONTAINER_EXTENSION_FILES", raising=False)
        monkeypatch.setenv("CONTAINER_EXTENSIONS", extensions_value)

        result = parse_container_extensions()
        assert len(result) == len(expected)
        for actual, expected_item in zip(result, expected):
            assert actual["id"] == expected_item["id"]
            if "bundle_name" in expected_item:
                assert actual["bundle_name"] == expected_item["bundle_name"]
            assert actual["args"] == expected_item["args"]

    def test_multiple_extension_files(self, monkeypatch, tmp_path):
        from common_python_tasks.env import parse_container_extensions

        ext1 = tmp_path / "Dockerfile.ext1"
        ext1.write_text("# ext1\nRUN echo ext1\n", encoding="utf-8")
        ext2 = tmp_path / "Dockerfile.ext2"
        ext2.write_text("# ext2\nRUN echo ext2\n", encoding="utf-8")

        monkeypatch.setenv("CONTAINER_EXTENSION_FILES", f"{ext1}:{ext2}")
        monkeypatch.delenv("CONTAINER_EXTENSIONS", raising=False)

        result = parse_container_extensions()

        assert len(result) == 2
        assert result[0]["id"] == "ext1"
        assert result[0]["source"] == "file"
        assert result[0]["path"] == str(ext1)
        assert result[1]["id"] == "ext2"
        assert result[1]["source"] == "file"
        assert result[1]["path"] == str(ext2)


class TestResolveExtensionContent:
    """Tests for resolve_extension_content (no template substitution)."""

    def test_template_contains_build_arg_variable(self, mock_load_data_file):
        from common_python_tasks.env import resolve_extension_content

        desc = {
            "id": "template_bundle",
            "source": "bundle",
            "path": None,
            "bundle_name": "template_bundle",
            "args": "jq curl",
        }
        content = resolve_extension_content(desc)
        assert "CONTAINER_APT_PACKAGES" in content
        assert "jq curl" not in content

    def test_missing_args_do_not_affect_content(self, mock_load_data_file):
        from common_python_tasks.env import resolve_extension_content

        desc = {
            "id": "template_bundle",
            "source": "bundle",
            "path": None,
            "bundle_name": "template_bundle",
            "args": None,
        }
        content = resolve_extension_content(desc)
        assert "CONTAINER_APT_PACKAGES" in content

    def test_file_extension_without_placeholder_and_no_args(self, tmp_path):
        from common_python_tasks.env import resolve_extension_content

        ext_file = tmp_path / "Dockerfile.custom"
        ext_file.write_text("RUN echo hello\n", encoding="utf-8")

        desc = {
            "id": "custom",
            "source": "file",
            "path": str(ext_file),
            "bundle_name": None,
            "args": None,
        }
        content = resolve_extension_content(desc)
        assert content == "RUN echo hello\n"


class TestParseContainerDeps:
    """Tests for parse_container_deps env var handling."""

    def test_returns_none_when_unset(self, monkeypatch):
        from common_python_tasks.env import parse_container_deps

        monkeypatch.delenv("CONTAINER_DEPS_CONTENT", raising=False)
        monkeypatch.delenv("CONTAINER_DEPS_FILE", raising=False)
        assert parse_container_deps() is None

    def test_returns_content_from_env(self, monkeypatch):
        from common_python_tasks.env import parse_container_deps

        monkeypatch.setenv("CONTAINER_DEPS_CONTENT", "RUN apt-get install -y curl")
        assert parse_container_deps() == "RUN apt-get install -y curl"

    def test_returns_content_from_file(self, monkeypatch, tmp_path):
        from common_python_tasks.env import parse_container_deps

        monkeypatch.delenv("CONTAINER_DEPS_CONTENT", raising=False)
        deps_file = tmp_path / "deps.Dockerfile"
        deps_file.write_text("RUN pip install boto3\n", encoding="utf-8")
        monkeypatch.setenv("CONTAINER_DEPS_FILE", str(deps_file))
        assert parse_container_deps() == "RUN pip install boto3"

    def test_returns_content_from_multiple_files(self, monkeypatch, tmp_path):
        from common_python_tasks.env import parse_container_deps

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
        from common_python_tasks.env import parse_container_deps_source

        deps_file = tmp_path / "deps.Dockerfile"
        deps_file.write_text("FROM FILE\n", encoding="utf-8")
        monkeypatch.delenv("CONTAINER_DEPS_CONTENT", raising=False)
        monkeypatch.setenv("CONTAINER_DEPS_FILE", str(deps_file))

        dockerfile_path, content = parse_container_deps_source()
        assert dockerfile_path == deps_file
        assert content is None

    def test_file_source_returns_paths_when_multiple_files(self, monkeypatch, tmp_path):
        from common_python_tasks.env import parse_container_deps_source

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
        from common_python_tasks.env import parse_container_deps_source

        deps_file = tmp_path / "deps.Dockerfile"
        deps_file.write_text("FROM FILE\n", encoding="utf-8")
        monkeypatch.setenv("CONTAINER_DEPS_CONTENT", "FROM ENV")
        monkeypatch.setenv("CONTAINER_DEPS_FILE", str(deps_file))

        dockerfile_path, content = parse_container_deps_source()
        assert dockerfile_path is None
        assert content == "FROM ENV"

    def test_file_missing_raises(self, monkeypatch):
        from common_python_tasks.env import parse_container_deps

        monkeypatch.delenv("CONTAINER_DEPS_CONTENT", raising=False)
        monkeypatch.setenv("CONTAINER_DEPS_FILE", "/nonexistent/deps.Dockerfile")
        with pytest.raises(SystemExit):
            parse_container_deps()

    def test_empty_content_returns_none(self, monkeypatch):
        from common_python_tasks.env import parse_container_deps

        monkeypatch.setenv("CONTAINER_DEPS_CONTENT", "   ")
        monkeypatch.delenv("CONTAINER_DEPS_FILE", raising=False)
        assert parse_container_deps() is None


class TestParseContainerDepsMappings:
    """Tests for parse_container_deps_mappings env var handling."""

    def test_returns_none_when_unset(self, monkeypatch):
        from common_python_tasks.env import parse_container_deps_mappings

        monkeypatch.delenv("CONTAINER_DEPS_MAPPINGS", raising=False)
        assert parse_container_deps_mappings() is None

    def test_parses_simple_mappings(self, monkeypatch):
        from common_python_tasks.env import parse_container_deps_mappings

        monkeypatch.setenv(
            "CONTAINER_DEPS_MAPPINGS",
            "dep1:/opt/dep1 dep2:/usr/local/bin/dep2",
        )
        assert parse_container_deps_mappings() == {
            "dep1": "/opt/dep1",
            "dep2": "/usr/local/bin/dep2",
        }

    def test_parses_quoted_paths(self, monkeypatch):
        from common_python_tasks.env import parse_container_deps_mappings

        monkeypatch.setenv(
            "CONTAINER_DEPS_MAPPINGS",
            "dep1:'/opt/dep one' dep2:\"/usr/local/bin/dep two\"",
        )
        assert parse_container_deps_mappings() == {
            "dep1": "/opt/dep one",
            "dep2": "/usr/local/bin/dep two",
        }

    def test_invalid_token_raises(self, monkeypatch, caplog):
        from common_python_tasks.env import parse_container_deps_mappings

        monkeypatch.setenv("CONTAINER_DEPS_MAPPINGS", "invalid-token")
        with pytest.raises(SystemExit):
            parse_container_deps_mappings()

        assert "invalid token: invalid-token" in caplog.text

    def test_duplicate_name_raises(self, monkeypatch):
        from common_python_tasks.env import parse_container_deps_mappings

        monkeypatch.setenv(
            "CONTAINER_DEPS_MAPPINGS",
            "dep1:/opt/dep1 dep1:/opt/dep2",
        )
        with pytest.raises(SystemExit):
            parse_container_deps_mappings()


class TestRenderDepsMoveScript:
    """Tests for generating the dependency move script."""

    def test_script_contains_expected_move_logic(self):
        from common_python_tasks.env import render_container_deps_move_script

        script = render_container_deps_move_script(
            {"dep1": "/opt/dep1", "dep2": "/usr/local/bin/dep2"}
        )
        assert "shutil.move" in script
        assert 'source_root = pathlib.Path("/tmp/deps")' in script
        assert "'dep1': '/opt/dep1'" in script
