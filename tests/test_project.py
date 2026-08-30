from importlib import metadata
from unittest.mock import MagicMock, patch

import pytest

from common_python_tasks.project import (
    extract_poe_script_tags,
    get_authors,
    get_build_command,
    get_dependency_update_command,
    get_installed_requirement_version,
    get_project_version,
    get_publish_command,
    get_release_tag_from_project_version,
    get_ruff_target_version,
    get_uv_version,
    is_task_tag_included,
)


def test_get_installed_requirement_version_strips_extras_and_normalizes_name():
    def version_side_effect(name):
        if name == "uv-dynamic-versioning":
            return "0.14.0"
        raise metadata.PackageNotFoundError

    get_installed_requirement_version.cache_clear()
    with patch("importlib.metadata.version", side_effect=version_side_effect):
        assert (
            get_installed_requirement_version("uv-dynamic-versioning[plugin]")
            == "0.14.0"
        )


def test_get_installed_requirement_version_uses_uv_run_when_metadata_fails():
    def version_side_effect(name):
        raise metadata.PackageNotFoundError

    get_installed_requirement_version.cache_clear()
    with (
        patch("importlib.metadata.version", side_effect=version_side_effect),
        patch(
            "common_python_tasks.utils.run_command",
            return_value=MagicMock(stdout="1.9.0\n", returncode=0),
        ),
    ):
        assert get_installed_requirement_version("example-package") == "1.9.0"


def test_get_installed_requirement_version_uses_uv_pip_show_when_uv_run_fails():
    def version_side_effect(name):
        raise metadata.PackageNotFoundError

    package_show_output = """
Name: example-package
Version: 1.8.3
"""

    get_installed_requirement_version.cache_clear()

    def run_command_side_effect(cmd, **kwargs):
        if cmd[:3] == ["uv", "run", "python"]:
            return MagicMock(stdout="", returncode=1)
        if cmd == ["uv", "pip", "show", "example-package"]:
            return MagicMock(stdout=package_show_output, returncode=0)
        return MagicMock(stdout="", returncode=1)

    with (
        patch("importlib.metadata.version", side_effect=version_side_effect),
        patch(
            "common_python_tasks.utils.run_command",
            side_effect=run_command_side_effect,
        ),
    ):
        assert get_installed_requirement_version("example-package") == "1.8.3"


def test_get_installed_requirement_version_returns_none_when_not_installed():
    def version_side_effect(name):
        raise metadata.PackageNotFoundError

    get_installed_requirement_version.cache_clear()
    with (
        patch("importlib.metadata.version", side_effect=version_side_effect),
        patch(
            "common_python_tasks.utils.run_command",
            return_value=MagicMock(stdout="", returncode=1),
        ),
    ):
        assert get_installed_requirement_version("no-such-package") is None


def test_get_ruff_target_version_from_requires_python():
    with patch(
        "common_python_tasks.project.read_pyproject_toml",
        return_value={"project": {"requires-python": ">=3.11,<4.0"}},
    ):
        assert get_ruff_target_version() == "py311"


@pytest.mark.parametrize("requires_python", [">=3.11.2,<4", "~=3.11.2"])
def test_get_ruff_target_version_supports_patch_level_constraints(requires_python):
    with patch(
        "common_python_tasks.project.read_pyproject_toml",
        return_value={"project": {"requires-python": requires_python}},
    ):
        assert get_ruff_target_version() == "py311"


def test_get_ruff_target_version_supports_single_digit_python_minor():
    with patch(
        "common_python_tasks.project.read_pyproject_toml",
        return_value={"project": {"requires-python": ">=3.7,<3.8"}},
    ):
        assert get_ruff_target_version() == "py37"


def test_get_ruff_target_version_returns_none_for_missing_requires_python():
    with patch(
        "common_python_tasks.project.read_pyproject_toml",
        return_value={"project": {}},
    ):
        assert get_ruff_target_version() is None


def test_get_ruff_target_version_returns_none_for_invalid_specifier():
    with patch(
        "common_python_tasks.project.read_pyproject_toml",
        return_value={"project": {"requires-python": "not-a-spec"}},
    ):
        assert get_ruff_target_version() is None


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

    with patch("common_python_tasks.project.read_pyproject_toml") as mock_toml:
        mock_toml.return_value = {"project": {"scripts": {"my-script": "pkg.cli:main"}}}

        result = resolve_container_entrypoint_command(entrypoint_script="  my-script  ")

    assert result == "my-script"


def test_resolve_container_entrypoint_command_custom_unknown_script_fails():
    from common_python_tasks.project import resolve_container_entrypoint_command

    with (
        patch("common_python_tasks.project.read_pyproject_toml") as mock_toml,
        patch(
            "common_python_tasks.utils.fatal", side_effect=SystemExit(1)
        ) as mock_fatal,
    ):
        mock_toml.return_value = {
            "project": {
                "scripts": {"my-api": "pkg.api:main", "my-worker": "pkg.worker:main"}
            }
        }

        with pytest.raises(SystemExit):
            resolve_container_entrypoint_command(entrypoint_script="unknown-script")

    assert mock_fatal.call_count == 1
    assert "Available scripts: my-api, my-worker" in mock_fatal.call_args.args[0]


def test_resolve_container_entrypoint_command_custom_unknown_script_fails_without_scripts():
    from common_python_tasks.project import resolve_container_entrypoint_command

    with (
        patch(
            "common_python_tasks.project.read_pyproject_toml",
            return_value={"project": {}},
        ),
        patch(
            "common_python_tasks.utils.fatal", side_effect=SystemExit(1)
        ) as mock_fatal,
        pytest.raises(SystemExit),
    ):
        resolve_container_entrypoint_command(entrypoint_script="unknown-script")

    assert mock_fatal.call_count == 1
    assert "No [project].scripts entries were found" in mock_fatal.call_args.args[0]


def test_resolve_container_entrypoint_command_uses_package_script_when_available():
    from common_python_tasks.project import resolve_container_entrypoint_command

    with (
        patch("common_python_tasks.project.read_pyproject_toml") as mock_toml,
        patch("common_python_tasks.utils.get_package_name", return_value="my_pkg"),
    ):
        mock_toml.return_value = {"project": {"scripts": {"my_pkg": "my_pkg.cli:main"}}}

        result = resolve_container_entrypoint_command()

        assert result == "my_pkg"


def test_resolve_container_entrypoint_command_defaults_to_python():
    from common_python_tasks.project import resolve_container_entrypoint_command

    with (
        patch("common_python_tasks.project.read_pyproject_toml") as mock_toml,
        patch("common_python_tasks.utils.get_package_name", return_value="my_pkg"),
    ):
        mock_toml.return_value = {"project": {}}

        result = resolve_container_entrypoint_command()

        assert result == "python"


def test_resolve_container_entrypoint_command_prefers_package_script_with_multiple_scripts():
    from common_python_tasks.project import resolve_container_entrypoint_command

    with (
        patch("common_python_tasks.project.read_pyproject_toml") as mock_toml,
        patch("common_python_tasks.utils.get_package_name", return_value="my_pkg"),
    ):
        mock_toml.return_value = {
            "project": {
                "scripts": {
                    "my-worker": "pkg.worker:main",
                    "my_pkg": "pkg.api:main",
                    "my-admin": "pkg.admin:main",
                }
            }
        }

        result = resolve_container_entrypoint_command()

        assert result == "my_pkg"


def test_resolve_container_entrypoint_command_falls_back_to_hyphenated_script():
    from common_python_tasks.project import resolve_container_entrypoint_command

    with (
        patch("common_python_tasks.project.read_pyproject_toml") as mock_toml,
        patch(
            "common_python_tasks.utils.get_package_name", return_value="some_package"
        ),
    ):
        mock_toml.return_value = {
            "project": {"scripts": {"some-package": "some_package.cli:main"}}
        }

        result = resolve_container_entrypoint_command()

        assert result == "some-package"


def test_resolve_container_entrypoint_command_prefers_underscore_over_hyphenated():
    from common_python_tasks.project import resolve_container_entrypoint_command

    with (
        patch("common_python_tasks.project.read_pyproject_toml") as mock_toml,
        patch(
            "common_python_tasks.utils.get_package_name", return_value="some_package"
        ),
    ):
        mock_toml.return_value = {
            "project": {
                "scripts": {
                    "some_package": "some_package.cli:main",
                    "some-package": "some_package.alt_cli:main",
                }
            }
        }

        result = resolve_container_entrypoint_command()

        assert result == "some_package"


def test_get_release_tag_from_project_version():
    with patch(
        "common_python_tasks.project.get_project_version",
        return_value="2.1.0",
    ):
        result = get_release_tag_from_project_version()

        assert result == "v2.1.0"


def test_get_uv_version_parses_output():
    get_uv_version.cache_clear()
    with patch(
        "common_python_tasks.utils.run_command",
        return_value=MagicMock(stdout="uv 0.8.0\n", returncode=0),
    ):
        assert get_uv_version() == "0.8.0"


def test_get_build_command():
    assert get_build_command() == ["uv", "build"]
    assert get_build_command(wheel_only=True) == ["uv", "build", "--wheel"]


def test_get_dependency_update_command():
    assert get_dependency_update_command() == ["uv", "sync", "--upgrade"]
    assert get_dependency_update_command(["pytest", "requests"]) == [
        "uv",
        "sync",
        "--upgrade",
        "--upgrade-package",
        "pytest",
        "--upgrade-package",
        "requests",
    ]


def test_get_publish_command_uses_uv():
    assert get_publish_command() == ["uv", "publish"]


def test_get_publish_command_uses_repository_name():
    assert get_publish_command(repository="internal") == [
        "uv",
        "publish",
        "--index",
        "internal",
    ]


def test_get_publish_command_uses_repository_url():
    assert get_publish_command(
        repository_url="https://packages.example.com/legacy/"
    ) == [
        "uv",
        "publish",
        "--publish-url",
        "https://packages.example.com/legacy/",
    ]


def test_get_publish_command_rejects_repository_and_url():
    with pytest.raises(SystemExit):
        get_publish_command(
            repository="internal",
            repository_url="https://packages.example.com/legacy/",
        )


def test_get_publish_command_uses_uv_publish_index_env_fallback(monkeypatch):
    monkeypatch.setenv("UV_PUBLISH_INDEX", "testpypi")
    assert get_publish_command() == [
        "uv",
        "publish",
        "--index",
        "testpypi",
    ]


def test_get_publish_command_prefers_package_publish_repository_env(monkeypatch):
    monkeypatch.setenv("COMMON_PYTHON_TASKS_PUBLISH_REPOSITORY", "internal")
    monkeypatch.setenv("UV_PUBLISH_INDEX", "testpypi")
    assert get_publish_command() == [
        "uv",
        "publish",
        "--index",
        "internal",
    ]


def test_get_publish_command_uses_uv_publish_url_env_fallback(monkeypatch):
    monkeypatch.setenv("UV_PUBLISH_URL", "https://packages.example.com/legacy/")
    assert get_publish_command() == [
        "uv",
        "publish",
        "--publish-url",
        "https://packages.example.com/legacy/",
    ]


def test_get_publish_command_uses_uv_config_default_publishable_index():
    with patch(
        "common_python_tasks.project.read_pyproject_toml",
        return_value={
            "tool": {
                "uv": {
                    "index": [
                        {
                            "name": "pypi",
                            "url": "https://pypi.org/simple",
                        },
                        {
                            "name": "internal",
                            "url": "https://packages.example.com/simple",
                            "publish-url": "https://packages.example.com/legacy/",
                            "default": True,
                        },
                    ]
                }
            }
        },
    ):
        assert get_publish_command() == [
            "uv",
            "publish",
            "--index",
            "internal",
        ]


def test_get_publish_command_rejects_ambiguous_uv_config_publish_indexes():
    with (
        patch(
            "common_python_tasks.project.read_pyproject_toml",
            return_value={
                "tool": {
                    "uv": {
                        "index": [
                            {
                                "name": "internal-a",
                                "url": "https://a.example.com/simple",
                                "publish-url": "https://a.example.com/legacy/",
                            },
                            {
                                "name": "internal-b",
                                "url": "https://b.example.com/simple",
                                "publish-url": "https://b.example.com/legacy/",
                            },
                        ]
                    }
                }
            },
        ),
        pytest.raises(SystemExit),
    ):
        get_publish_command()


def test_get_publish_command_explicit_repository_overrides_defaults(monkeypatch):
    monkeypatch.setenv("UV_PUBLISH_INDEX", "from-env")
    assert get_publish_command(repository="from-arg") == [
        "uv",
        "publish",
        "--index",
        "from-arg",
    ]


def test_get_project_version_prefers_vcs_when_pyproject_is_placeholder():
    with (
        patch(
            "common_python_tasks.project.read_pyproject_toml",
            return_value={"project": {"version": "0.0.0"}},
        ),
        patch(
            "common_python_tasks.project.get_project_version_from_vcs",
            return_value="1.4.2",
        ),
    ):
        assert get_project_version() == "1.4.2"


def test_get_project_version_prefers_static_project_metadata():
    with (
        patch(
            "common_python_tasks.project.read_pyproject_toml",
            return_value={"project": {"version": "1.5.0"}},
        ),
        patch(
            "common_python_tasks.project.get_project_version_from_vcs",
            return_value="2.0.0",
        ),
    ):
        assert get_project_version() == "1.5.0"
