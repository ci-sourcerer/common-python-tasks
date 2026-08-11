import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from common_python_tasks.github import (
    GitHubClient,
    get_github_api_base_url,
    get_github_release_asset_paths,
    get_github_repository,
    get_github_token,
    upload_github_release_asset,
)


def test_get_github_token_uses_environment_variable(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")

    assert get_github_token() == "env-token"


def test_get_github_token_uses_updated_environment_variable(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "first-token")
    assert get_github_token() == "first-token"

    monkeypatch.setenv("GITHUB_TOKEN", "second-token")
    assert get_github_token() == "second-token"


def test_get_github_token_falls_back_to_gh_cli(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    completed_process = subprocess.CompletedProcess(
        args=["gh", "auth", "token"], returncode=0, stdout="cli-token\n", stderr=""
    )

    monkeypatch.setattr(
        "common_python_tasks.github.utils.run_command",
        lambda *args, **kwargs: completed_process,
    )

    assert get_github_token() == "cli-token"


def test_get_github_token_caches_gh_cli_lookup(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    run_command = Mock(
        return_value=subprocess.CompletedProcess(
            args=["gh", "auth", "token"],
            returncode=0,
            stdout="cli-token\n",
            stderr="",
        )
    )
    monkeypatch.setattr("common_python_tasks.github.utils.run_command", run_command)

    assert get_github_token() == "cli-token"
    assert get_github_token() == "cli-token"
    run_command.assert_called_once()


def test_get_github_token_warns_when_gh_cli_is_missing(monkeypatch, caplog):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    def raise_missing(*args, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr("common_python_tasks.github.utils.run_command", raise_missing)

    caplog.set_level("WARNING")
    assert get_github_token() is None
    assert "GitHub CLI not installed" in caplog.text


def test_get_github_token_warns_when_gh_cli_fails(monkeypatch, caplog):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    completed_process = subprocess.CompletedProcess(
        args=["gh", "auth", "token"], returncode=1, stdout="", stderr="error\n"
    )

    monkeypatch.setattr(
        "common_python_tasks.github.utils.run_command",
        lambda *args, **kwargs: completed_process,
    )

    caplog.set_level("WARNING")
    assert get_github_token() is None
    assert "Failed to retrieve GitHub token" in caplog.text


def test_get_github_api_base_url_uses_environment_variable(monkeypatch):
    monkeypatch.setenv("GITHUB_API_URL", "https://example.com/api/")
    monkeypatch.delenv("GITHUB_SERVER_URL", raising=False)

    assert get_github_api_base_url() == "https://example.com/api"


def test_get_github_api_base_url_uses_updated_environment_variable(monkeypatch):
    monkeypatch.setenv("GITHUB_API_URL", "https://first.example.com/api")
    assert get_github_api_base_url() == "https://first.example.com/api"

    monkeypatch.setenv("GITHUB_API_URL", "https://second.example.com/api")
    assert get_github_api_base_url() == "https://second.example.com/api"


def test_get_github_repository_caches_remote_lookup(monkeypatch, tmp_path):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.chdir(tmp_path)
    run_command = Mock(
        return_value=subprocess.CompletedProcess(
            args=["git", "remote", "get-url", "origin"],
            returncode=0,
            stdout="https://github.com/owner/repo.git\n",
            stderr="",
        )
    )
    monkeypatch.setattr("common_python_tasks.github.utils.run_command", run_command)

    assert get_github_repository() == "owner/repo"
    assert get_github_repository() == "owner/repo"
    run_command.assert_called_once()


def test_get_github_api_base_url_defaults_to_github_com(monkeypatch):
    monkeypatch.delenv("GITHUB_API_URL", raising=False)
    monkeypatch.delenv("GITHUB_SERVER_URL", raising=False)

    assert get_github_api_base_url() == "https://api.github.com"


def test_get_github_api_base_url_uses_enterprise_api_path(monkeypatch):
    monkeypatch.delenv("GITHUB_API_URL", raising=False)
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://ghe.example.com/")

    assert get_github_api_base_url() == "https://ghe.example.com/api/v3"


def test_github_client_build_url_uses_selected_endpoint(monkeypatch):
    monkeypatch.delenv("GITHUB_API_URL", raising=False)
    monkeypatch.delenv("GITHUB_SERVER_URL", raising=False)

    client = GitHubClient(repository="owner/repo", token="token")

    assert (
        client._build_url("/releases", endpoint="api")
        == "https://api.github.com/repos/owner/repo/releases"
    )
    assert (
        client._build_url("/releases/1/assets", endpoint="uploads")
        == "https://uploads.github.com/repos/owner/repo/releases/1/assets"
    )


def test_get_github_release_asset_paths_supports_quoted_colon_delimited_env(
    monkeypatch,
    tmp_path,
):
    asset_a = tmp_path / "dist one.txt"
    asset_b = tmp_path / "other.txt"
    asset_a.write_text("x", encoding="utf-8")
    asset_b.write_text("y", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_RELEASE_ASSETS", '"dist one.txt":other.txt')

    result = get_github_release_asset_paths()

    assert result == [Path("dist one.txt"), Path("other.txt")]


def test_get_github_release_asset_paths_returns_no_assets_for_empty_asset_list(
    monkeypatch,
    tmp_path,
):
    asset = tmp_path / "dist" / "package.whl"
    asset.parent.mkdir()
    asset.write_text("wheel", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_RELEASE_ASSETS", raising=False)

    result = get_github_release_asset_paths([])

    assert result == []


def test_upload_github_release_asset_reports_missing_path(tmp_path, caplog):
    missing_asset = tmp_path / "missing.whl"

    with pytest.raises(SystemExit):
        upload_github_release_asset(1, missing_asset)

    assert f"GitHub Release asset not found: {missing_asset}" in caplog.text
