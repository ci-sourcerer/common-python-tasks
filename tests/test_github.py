import subprocess

from common_python_tasks.github import get_github_token


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
