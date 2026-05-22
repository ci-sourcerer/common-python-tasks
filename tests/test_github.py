import subprocess

from common_python_tasks.github import (
    GitHubClient,
    get_github_api_base_url,
    get_github_token,
)


def test_get_github_token_uses_environment_variable(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")

    assert get_github_token() == "env-token"


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
