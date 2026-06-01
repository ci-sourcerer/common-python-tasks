import importlib.metadata as metadata
from unittest.mock import MagicMock, patch

import pytest
from common_python_tasks.project import (
    extract_poe_script_tags,
    get_authors,
    get_black_target_version,
    get_installed_requirement_version,
    is_task_tag_included,
)


def test_get_installed_requirement_version_strips_extras_and_normalizes_name():
    def version_side_effect(name):
        if name == "poetry-dynamic-versioning":
            return "0.17.0"
        raise metadata.PackageNotFoundError

    get_installed_requirement_version.cache_clear()
    with patch("importlib.metadata.version", side_effect=version_side_effect):
        assert (
            get_installed_requirement_version("poetry-dynamic-versioning[plugin]")
            == "0.17.0"
        )


def test_get_installed_requirement_version_uses_poetry_show_when_not_available_in_metadata():
    def version_side_effect(name):
        raise metadata.PackageNotFoundError

    poetry_show_output = """
 name         : poetry-dynamic-versioning
 version      : 1.8.2
 description  : Plugin for Poetry to enable dynamic versioning based on VCS tags
"""

    get_installed_requirement_version.cache_clear()

    def run_command_side_effect(
        cmd, capture_output=True, acceptable_returncodes=None, env=None
    ):
        if cmd[:3] == ["poetry", "run", "python"]:
            return MagicMock(stdout="", returncode=1)
        if cmd == ["poetry", "show", "poetry-dynamic-versioning"]:
            return MagicMock(stdout=poetry_show_output, returncode=0)
        return MagicMock(stdout="", returncode=1)

    with (
        patch("importlib.metadata.version", side_effect=version_side_effect),
        patch(
            "common_python_tasks.project.get_local_poetry_plugin_version",
            return_value=None,
        ),
        patch(
            "common_python_tasks.utils.run_command",
            side_effect=run_command_side_effect,
        ),
    ):
        assert (
            get_installed_requirement_version("poetry-dynamic-versioning[plugin]")
            == "1.8.2"
        )


def test_get_installed_requirement_version_uses_poetry_self_show_when_poetry_show_fails():
    def version_side_effect(name):
        raise metadata.PackageNotFoundError

    poetry_self_show_output = """
 name         : poetry-dynamic-versioning
 version      : 1.8.3
 description  : Plugin for Poetry to enable dynamic versioning based on VCS tags
"""

    get_installed_requirement_version.cache_clear()

    def run_command_side_effect(
        cmd, capture_output=True, acceptable_returncodes=None, env=None
    ):
        if cmd[:3] == ["poetry", "run", "python"]:
            return MagicMock(stdout="", returncode=1)
        if cmd == ["poetry", "show", "poetry-dynamic-versioning"]:
            return MagicMock(stdout="", returncode=1)
        if cmd == ["poetry", "self", "show", "poetry-dynamic-versioning"]:
            return MagicMock(stdout=poetry_self_show_output, returncode=0)
        return MagicMock(stdout="", returncode=1)

    with (
        patch("importlib.metadata.version", side_effect=version_side_effect),
        patch(
            "common_python_tasks.project.get_local_poetry_plugin_version",
            return_value=None,
        ),
        patch(
            "common_python_tasks.utils.run_command",
            side_effect=run_command_side_effect,
        ),
    ):
        assert (
            get_installed_requirement_version("poetry-dynamic-versioning[plugin]")
            == "1.8.3"
        )


def test_get_installed_requirement_version_uses_poetry_run_python_when_metadata_fails():
    def version_side_effect(name):
        raise metadata.PackageNotFoundError

    get_installed_requirement_version.cache_clear()
    with (
        patch("importlib.metadata.version", side_effect=version_side_effect),
        patch(
            "common_python_tasks.project.get_local_poetry_plugin_version",
            return_value=None,
        ),
        patch(
            "common_python_tasks.utils.run_command",
            return_value=MagicMock(stdout="1.9.0\n", returncode=0),
        ),
    ):
        assert get_installed_requirement_version("poetry-plugin-export") == "1.9.0"


def test_get_installed_requirement_version_uses_local_poetry_plugins_directory(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    metadata_dir = (
        tmp_path / ".poetry" / "plugins" / "poetry_plugin_export-1.10.0.dist-info"
    )
    metadata_dir.mkdir(parents=True)
    metadata_dir.joinpath("METADATA").write_text(
        "Name: poetry-plugin-export\nVersion: 1.10.0\n", encoding="utf-8"
    )

    def version_side_effect(name):
        raise metadata.PackageNotFoundError

    get_installed_requirement_version.cache_clear()
    with patch("importlib.metadata.version", side_effect=version_side_effect):
        assert get_installed_requirement_version("poetry-plugin-export") == "1.10.0"


def test_get_installed_requirement_version_returns_none_when_not_installed():
    def version_side_effect(name):
        raise metadata.PackageNotFoundError

    get_installed_requirement_version.cache_clear()
    with patch("importlib.metadata.version", side_effect=version_side_effect):
        assert get_installed_requirement_version("no-such-package") is None


def test_get_black_target_version_from_requires_python():
    with patch(
        "common_python_tasks.project.read_pyproject_toml",
        return_value={"project": {"requires-python": ">=3.11,<4.0"}},
    ):
        assert get_black_target_version() == "py311"


def test_get_black_target_version_returns_none_for_missing_requires_python():
    with patch(
        "common_python_tasks.project.read_pyproject_toml",
        return_value={"project": {}},
    ):
        assert get_black_target_version() is None


def test_get_black_target_version_returns_none_for_invalid_specifier():
    with patch(
        "common_python_tasks.project.read_pyproject_toml",
        return_value={"project": {"requires-python": "not-a-spec"}},
    ):
        assert get_black_target_version() is None


def test_is_task_tag_included_with_include_tags():
    is_task_tag_included.cache_clear()
    with patch("common_python_tasks.project.read_pyproject_toml") as mock_toml:
        mock_toml.return_value = {
            "tool": {
                "poe": {
                    "include_script": "common_python_tasks:tasks(include_tags=['format', 'containers'])"
                }
            }
        }

        assert is_task_tag_included("containers") is True
        assert is_task_tag_included("common") is False


def test_extract_poe_script_tags_with_include_and_exclude_scripts():
    include_tags, exclude_tags = extract_poe_script_tags(
        include_script="common_python_tasks:tasks(include_tags=['format', 'containers'])",
        exclude_script="common_python_tasks:tasks(exclude_tags=['fastapi'])",
    )

    assert include_tags == {"format", "containers"}
    assert exclude_tags == {"fastapi"}


def test_is_task_tag_included_with_common_include_tag():
    is_task_tag_included.cache_clear()
    with patch("common_python_tasks.project.read_pyproject_toml") as mock_toml:
        mock_toml.return_value = {
            "tool": {
                "poe": {
                    "include_script": "common_python_tasks:tasks(include_tags=['common'])"
                }
            }
        }

        assert is_task_tag_included("common") is True
        assert is_task_tag_included("containers") is False


def test_is_task_tag_included_with_exclude_tags():
    is_task_tag_included.cache_clear()
    with patch("common_python_tasks.project.read_pyproject_toml") as mock_toml:
        mock_toml.return_value = {
            "tool": {
                "poe": {
                    "exclude_script": "common_python_tasks:tasks(exclude_tags=['containers', 'fastapi'])"
                }
            }
        }

        assert is_task_tag_included("containers") is False


def test_extract_poe_script_tags_falls_back_to_exclude_tags_in_include_script():
    include_tags, exclude_tags = extract_poe_script_tags(
        include_script="common_python_tasks:tasks(exclude_tags=['containers'])",
    )

    assert include_tags is None
    assert exclude_tags == {"containers"}


def test_is_task_tag_included_defaults_true_without_filters():
    is_task_tag_included.cache_clear()
    with patch("common_python_tasks.project.read_pyproject_toml") as mock_toml:
        mock_toml.return_value = {
            "tool": {"poe": {"include_script": "common_python_tasks:tasks()"}}
        }

        assert is_task_tag_included("containers") is True


def test_get_authors_reads_pyproject():
    get_authors.cache_clear()
    with patch("common_python_tasks.project.read_pyproject_toml") as mock_toml:
        mock_toml.return_value = {
            "project": {
                "authors": [{"name": "Test Author", "email": "test@example.com"}]
            }
        }

        assert get_authors() == [("Test Author", "test@example.com")]


def test_resolve_container_entrypoint_command_uses_custom_when_provided():
    from common_python_tasks.project import resolve_container_entrypoint_command

    result = resolve_container_entrypoint_command(custom_entrypoint="  my-script  ")

    assert result == "my-script"


def test_resolve_container_entrypoint_command_uses_package_script_when_available():
    from common_python_tasks.project import resolve_container_entrypoint_command

    with patch("common_python_tasks.project.read_pyproject_toml") as mock_toml:
        with patch("common_python_tasks.utils.get_package_name", return_value="my_pkg"):
            mock_toml.return_value = {
                "project": {"scripts": {"my_pkg": "my_pkg.cli:main"}}
            }

            result = resolve_container_entrypoint_command()

            assert result == "my_pkg"


def test_resolve_container_entrypoint_command_defaults_to_python():
    from common_python_tasks.project import resolve_container_entrypoint_command

    with patch("common_python_tasks.project.read_pyproject_toml") as mock_toml:
        with patch("common_python_tasks.utils.get_package_name", return_value="my_pkg"):
            mock_toml.return_value = {"project": {}}

            result = resolve_container_entrypoint_command()

            assert result == "python"


def test_get_project_version_from_poetry_parses_output():
    from common_python_tasks.project import get_project_version_from_poetry

    with patch("common_python_tasks.utils.run_command") as mock_run:
        mock_run.return_value = MagicMock(stdout="my-project 1.2.3\n", returncode=0)

        result = get_project_version_from_poetry()

        assert result == "1.2.3"


def test_get_project_version_from_poetry_fails_on_empty_output():
    from common_python_tasks.project import get_project_version_from_poetry

    with patch("common_python_tasks.utils.run_command") as mock_run:
        with patch("common_python_tasks.utils.fatal", side_effect=SystemExit(1)):
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            with pytest.raises(SystemExit):
                get_project_version_from_poetry()


def test_get_release_tag_from_poetry_version():
    from common_python_tasks.project import get_release_tag_from_poetry_version

    with patch(
        "common_python_tasks.project.get_project_version_from_poetry",
        return_value="2.1.0",
    ):
        result = get_release_tag_from_poetry_version()

        assert result == "v2.1.0"
