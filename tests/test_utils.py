from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from common_python_tasks.utils import (
    compose_image_name,
    fatal,
    get_container_registry_url,
    get_package_name,
    get_ruff_config_path,
    is_package_installed,
    load_data_file,
    normalize_registry,
    parse_image_reference,
    prepend_changelog,
    require_package,
    run_command,
    run_git_cliff,
)


def test_is_package_installed_when_installed(mock_find_spec):
    mock_find_spec.return_value = MagicMock()

    is_package_installed.cache_clear()

    assert is_package_installed("ruff") is True
    mock_find_spec.assert_called_with("ruff")


def test_is_package_installed_when_not_installed(mock_find_spec):
    mock_find_spec.return_value = None

    is_package_installed.cache_clear()

    assert is_package_installed("ruff") is False
    mock_find_spec.assert_called_with("ruff")


def test_is_package_installed_handles_dashes(mock_find_spec):
    mock_find_spec.return_value = MagicMock()

    is_package_installed.cache_clear()

    assert is_package_installed("pytest-cov") is True
    mock_find_spec.assert_called_with("pytest_cov")


def test_is_package_installed_caches_results(mock_find_spec):
    mock_find_spec.return_value = MagicMock()

    is_package_installed.cache_clear()

    is_package_installed("ruff")
    is_package_installed("ruff")

    assert mock_find_spec.call_count == 1


def test_get_package_name_reads_pyproject_when_env_missing(monkeypatch):
    monkeypatch.delenv("PACKAGE_NAME", raising=False)
    get_package_name.cache_clear()
    with patch(
        "common_python_tasks.utils.Path.read_text",
        return_value='[project]\nname = "test-package"\n',
    ):
        assert get_package_name() == "test-package"


def test_normalize_registry_strips_scheme_and_slashes():
    assert normalize_registry("https://ghcr.io/org/") == "ghcr.io/org"
    assert (
        normalize_registry("http://registry.example.com:5000/")
        == "registry.example.com:5000"
    )
    assert normalize_registry("docker.io") == "docker.io"
    assert normalize_registry(None) is None


def test_parse_image_reference_parses_registry_namespace_repository_tag():
    result = parse_image_reference("ghcr.io/org/repo:1.2.3")

    assert result == {
        "registry": "ghcr.io",
        "namespace": "org",
        "repository": "repo",
        "tag": "1.2.3",
        "digest": None,
    }


def test_parse_image_reference_parses_short_names():
    assert parse_image_reference("repo:latest") == {
        "registry": None,
        "namespace": None,
        "repository": "repo",
        "tag": "latest",
        "digest": None,
    }
    assert parse_image_reference("user/repo:latest") == {
        "registry": None,
        "namespace": "user",
        "repository": "repo",
        "tag": "latest",
        "digest": None,
    }


def test_compose_image_name_creates_fully_qualified_reference():
    assert (
        compose_image_name("repo", "1.0", registry="ghcr.io", namespace="org")
        == "ghcr.io/org/repo:1.0"
    )
    assert (
        compose_image_name("repo", "1.0", registry="ghcr.io/org")
        == "ghcr.io/org/repo:1.0"
    )
    assert compose_image_name("repo", "1.0", namespace="org") == "org/repo:1.0"
    assert compose_image_name("repo", "1.0", fully_qualified=False) == "repo:1.0"


def test_get_container_registry_url_appends_namespace_to_host_only_registry(
    monkeypatch,
):
    monkeypatch.setenv("CONTAINER_REGISTRY_URL", "ghcr.io")
    monkeypatch.setenv("CONTAINER_REGISTRY_NAMESPACE", "acme")

    assert get_container_registry_url() == "ghcr.io/acme"


def test_get_container_registry_url_ignores_namespace_when_registry_includes_path(
    monkeypatch,
):
    monkeypatch.setenv("CONTAINER_REGISTRY_URL", "ghcr.io/acme")
    monkeypatch.setenv("CONTAINER_REGISTRY_NAMESPACE", "other")

    assert get_container_registry_url() == "ghcr.io/acme"


def test_run_command_executes_shell_command():
    with patch("common_python_tasks.utils.subprocess.run") as mock_subprocess:
        mock_subprocess.return_value = MagicMock(returncode=0, stdout="")
        run_command(["sh", "-lc", "echo hello"], env={"RELEASE_VERSION": "1.2.3"})

        mock_subprocess.assert_called_once()


def test_run_command_logs_dry_run():
    with patch("common_python_tasks.utils.log_dry_run") as mock_log:
        result = run_command(["sh", "-lc", "echo hello"], dry_run=True)

        assert result is None
        mock_log.assert_called_once_with("Would run command: %s", "sh -lc echo hello")


def test_fatal_logs_and_exits():
    with patch("common_python_tasks.utils.LOGGER") as mock_logger:
        with pytest.raises(SystemExit) as exc_info:
            fatal("Test error message")

        mock_logger.critical.assert_called_once_with("Test error message")
        assert exc_info.value.code == 1


def test_fatal_with_custom_exit_code():
    with patch("common_python_tasks.utils.LOGGER"):
        with pytest.raises(SystemExit) as exc_info:
            fatal("Test error", exit_code=42)

        assert exc_info.value.code == 42


def test_require_package_succeeds_when_installed(mock_find_spec):
    mock_find_spec.return_value = MagicMock()
    is_package_installed.cache_clear()

    require_package("ruff")


def test_require_package_fails_when_not_installed(mock_find_spec):
    mock_find_spec.return_value = None
    is_package_installed.cache_clear()

    with patch("common_python_tasks.utils.LOGGER"):
        with pytest.raises(SystemExit) as exc_info:
            require_package("ruff")

        assert exc_info.value.code == 1


def test_get_ruff_config_path_prefers_environment_override(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".ruff.toml").write_text("line-length = 100\n")
    monkeypatch.setenv("RUFF_CONFIG", "config/custom-ruff.toml")

    assert get_ruff_config_path() == (Path("config/custom-ruff.toml"), False)


@pytest.mark.parametrize("filename", [".ruff.toml", "ruff.toml"])
def test_get_ruff_config_path_uses_native_toml_discovery(
    filename, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / filename).write_text("line-length = 100\n")

    assert get_ruff_config_path() == (None, False)


def test_get_ruff_config_path_discovers_pyproject_ruff_table(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n")

    assert get_ruff_config_path() == (None, False)


def test_get_ruff_config_path_discovers_parent_configuration(tmp_path, monkeypatch):
    (tmp_path / "ruff.toml").write_text("line-length = 100\n")
    (tmp_path / "child").mkdir()
    monkeypatch.chdir(tmp_path / "child")

    assert get_ruff_config_path() == (None, False)


def test_get_ruff_config_path_falls_back_to_bundled_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with patch(
        "common_python_tasks.utils.load_data_file",
        return_value=(Path("/bundled/ruff.toml"), ""),
    ):
        assert get_ruff_config_path() == (Path("/bundled/ruff.toml"), True)


def test_bundled_ruff_config_is_available():
    _, contents = load_data_file("ruff.toml")

    assert contents


def test_alembic_template_uses_ruff_post_write_hooks():
    _, contents = load_data_file("alembic.ini.j2", type_identifier="fastapi")

    assert "hooks = ruff_check,ruff_format" in contents
    assert "ruff_check.options = check --fix-only --select F401,I" in contents
    assert "ruff_format.options = format REVISION_SCRIPT_FILENAME" in contents


def test_run_git_cliff_passes_args_and_capture_output_to_run_command():
    with (
        patch(
            "common_python_tasks.utils.get_config_path", return_value=Path("cliff.toml")
        ),
        patch("common_python_tasks.utils.run_command") as mock_run_command,
    ):
        mock_run_command.return_value = MagicMock(stdout="notes", returncode=0)

        result = run_git_cliff(["--unreleased"], capture_output=True)

        mock_run_command.assert_called_once_with(
            ["git-cliff", "--config", Path("cliff.toml"), "--unreleased"],
            capture_output=True,
            acceptable_returncodes={0},
        )
        assert result.stdout == "notes"


def test_run_git_cliff_defaults_to_no_capture():
    with (
        patch(
            "common_python_tasks.utils.get_config_path", return_value=Path("cliff.toml")
        ),
        patch("common_python_tasks.utils.run_command") as mock_run_command,
    ):
        run_git_cliff(["--tag", "v1.0.0"])

        mock_run_command.assert_called_once_with(
            ["git-cliff", "--config", Path("cliff.toml"), "--tag", "v1.0.0"],
            capture_output=False,
            acceptable_returncodes={0},
        )


def test_prepend_changelog_creates_scaffold_when_file_missing(tmp_path):
    changelog_path = tmp_path / "CHANGELOG.md"

    with (
        patch(
            "common_python_tasks.utils.get_config_path", return_value=Path("cliff.toml")
        ),
        patch("common_python_tasks.utils.run_command") as mock_run_command,
    ):
        mock_run_command.return_value = MagicMock(stdout="## [1.2.3] - 2026-05-22")
        prepend_changelog("v1.2.3", changelog_path)

    assert changelog_path.read_text(encoding="utf-8") == (
        "## [1.2.3] - 2026-05-22\n\n# Changelog\n\n## [Unreleased]\n"
    )
    mock_run_command.assert_called_once_with(
        [
            "git-cliff",
            "--config",
            Path("cliff.toml"),
            "--unreleased",
            "--tag",
            "v1.2.3",
        ],
        capture_output=True,
        acceptable_returncodes={0},
    )


def test_prepend_changelog_does_not_overwrite_existing_file(tmp_path):
    changelog_path = tmp_path / "CHANGELOG.md"
    changelog_path.write_text("# Existing Changelog\n", encoding="utf-8")

    with (
        patch(
            "common_python_tasks.utils.get_config_path", return_value=Path("cliff.toml")
        ),
        patch("common_python_tasks.utils.run_command") as mock_run_command,
    ):
        mock_run_command.return_value = MagicMock(stdout="## [2.0.0] - 2026-05-22\n")
        prepend_changelog("v2.0.0", changelog_path)

    assert changelog_path.read_text(encoding="utf-8") == (
        "## [2.0.0] - 2026-05-22\n\n# Existing Changelog\n"
    )
    mock_run_command.assert_called_once_with(
        [
            "git-cliff",
            "--config",
            Path("cliff.toml"),
            "--unreleased",
            "--tag",
            "v2.0.0",
        ],
        capture_output=True,
        acceptable_returncodes={0},
    )


def test_prepend_changelog_adds_trailing_newline_to_generated_section(tmp_path):
    changelog_path = tmp_path / "CHANGELOG.md"
    changelog_path.write_text("# Existing Changelog", encoding="utf-8")

    with (
        patch(
            "common_python_tasks.utils.get_config_path", return_value=Path("cliff.toml")
        ),
        patch("common_python_tasks.utils.run_command") as mock_run_command,
    ):
        mock_run_command.return_value = MagicMock(stdout="## [2.0.0] - 2026-05-22")
        prepend_changelog("v2.0.0", changelog_path)

    assert changelog_path.read_text(encoding="utf-8") == (
        "## [2.0.0] - 2026-05-22\n\n# Existing Changelog"
    )
    mock_run_command.assert_called_once_with(
        [
            "git-cliff",
            "--config",
            Path("cliff.toml"),
            "--unreleased",
            "--tag",
            "v2.0.0",
        ],
        capture_output=True,
        acceptable_returncodes={0},
    )


def test_prepend_changelog_uses_changelog_md_as_default_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with (
        patch(
            "common_python_tasks.utils.get_config_path", return_value=Path("cliff.toml")
        ),
        patch("common_python_tasks.utils.run_command") as mock_run_command,
    ):
        mock_run_command.return_value = MagicMock(stdout="## [1.0.0] - 2026-05-22\n")
        prepend_changelog("v1.0.0")

    assert (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8") == (
        "## [1.0.0] - 2026-05-22\n\n# Changelog\n\n## [Unreleased]\n"
    )
    mock_run_command.assert_called_once_with(
        [
            "git-cliff",
            "--config",
            Path("cliff.toml"),
            "--unreleased",
            "--tag",
            "v1.0.0",
        ],
        capture_output=True,
        acceptable_returncodes={0},
    )


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


def test_confirm_loops_until_valid_response():
    from common_python_tasks.utils import confirm

    with patch("builtins.input", side_effect=["maybe", "Y"]):
        assert confirm("Proceed?") is True

    with patch("builtins.input", side_effect=["", "no"]):
        assert confirm("Proceed?") is False
