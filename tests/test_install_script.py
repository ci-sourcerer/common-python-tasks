import os
import subprocess
import sys
import tomllib
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "add_common_python_tasks.py"
)


def _write_command_stub(bin_dir: Path, command: str) -> None:
    stub_path = bin_dir / command
    stub_path.write_text(
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$0 $*" >>"$CALL_LOG"\n'
        'if [ "$(basename "$0")" = "poe" ]; then\n'
        "    printf 'Configured tasks:\\n  test  Run tests\\n'\n"
        "fi\n",
        encoding="utf-8",
    )
    stub_path.chmod(0o755)


def _run_installer(
    project_dir: Path, monkeypatch, manager: str | None = None
) -> list[str]:
    bin_dir = project_dir / "bin"
    bin_dir.mkdir(exist_ok=True)
    call_log = project_dir / "calls.log"
    _write_command_stub(bin_dir, "uv")
    _write_command_stub(bin_dir, "poetry")
    _write_command_stub(bin_dir, "poe")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("CALL_LOG", str(call_log))
    if manager is not None:
        monkeypatch.setenv("COMMON_PYTHON_TASKS_PACKAGE_MANAGER", manager)
    else:
        monkeypatch.delenv("COMMON_PYTHON_TASKS_PACKAGE_MANAGER", raising=False)

    subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=project_dir,
        check=True,
        shell=False,
    )

    return call_log.read_text(encoding="utf-8").splitlines()


def test_installer_updates_existing_poe_table_idempotently(tmp_path, monkeypatch):
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        "[project]\n"
        'name = "example"\n'
        'version = "0.1.0"\n\n'
        "[tool.poe]\n"
        "sequence = true\n",
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").touch()

    _run_installer(tmp_path, monkeypatch, "uv")
    _run_installer(tmp_path, monkeypatch, "uv")

    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    assert pyproject["tool"]["poe"] == {
        "sequence": True,
        "include_script": "common_python_tasks:tasks()",
    }


def test_installer_uses_poetry_with_pinned_version(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n" 'name = "example"\n' 'version = "0.1.0"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("COMMON_PYTHON_TASKS_VERSION", "1.2.3")

    calls = _run_installer(tmp_path, monkeypatch, "poetry")

    assert any(
        call.endswith("poetry add --group dev common-python-tasks==1.2.3")
        for call in calls
    )


def test_installer_writes_include_script_for_tags_to_include(tmp_path, monkeypatch):
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        "[project]\n" 'name = "example"\n' 'version = "0.1.0"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("TAGS_TO_INCLUDE", "db redis")
    (tmp_path / "poetry.lock").touch()

    _run_installer(tmp_path, monkeypatch, "poetry")

    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    assert (
        pyproject["tool"]["poe"]["include_script"]
        == "common_python_tasks:tasks(include_tags=['db', 'redis'])"
    )


def test_installer_selects_package_manager_from_lock_file(tmp_path, monkeypatch):
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        "[project]\n" 'name = "example"\n' 'version = "0.1.0"\n',
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").touch()

    calls = _run_installer(tmp_path, monkeypatch, None)

    assert any(call.endswith("uv add --dev common-python-tasks") for call in calls)
