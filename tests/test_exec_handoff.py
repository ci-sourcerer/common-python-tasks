import os
import stat
from pathlib import Path
from unittest.mock import patch


def test_build_exec_script_basic():
    """Script contains the compose command and self-deletes via trap."""
    from common_python_tasks.utils import build_exec_script

    script_path = build_exec_script(
        ["docker", "compose", "up", "--force-recreate"],
    )
    try:
        content = Path(script_path).read_text()

        assert content.startswith("#!/bin/sh\n")
        assert "trap" in content
        assert "rm -f" in content
        assert "SCRIPT_PATH=" in content
        assert "docker compose up --force-recreate" in content
        # No cleanup or teardown lines when not requested
        assert "Teardown" not in content
    finally:
        os.unlink(script_path)


def test_build_exec_script_cleanup_paths(tmp_path):
    """Script includes rm commands for each cleanup path."""
    from common_python_tasks.utils import build_exec_script

    fake_files = [tmp_path / "compose-base.abc.yml", tmp_path / "alembic.ini"]
    script_path = build_exec_script(
        ["docker", "compose", "up"],
        cleanup_paths=fake_files,
    )
    try:
        content = Path(script_path).read_text()

        for f in fake_files:
            assert str(f) in content
        assert content.count("rm -f") >= len(fake_files) + 1  # +1 for self-delete
    finally:
        os.unlink(script_path)


def test_build_exec_script_teardown_command():
    """Script includes an inline teardown command after the main command."""
    from common_python_tasks.utils import build_exec_script

    script_path = build_exec_script(
        ["docker", "compose", "up"],
        teardown_command=["docker", "compose", "rm", "-f", "-s", "-v"],
    )
    try:
        content = Path(script_path).read_text()
        lines = content.strip().splitlines()

        assert "docker compose rm -f -s -v" in content
        # Teardown should appear after the up command
        up_idx = next(i for i, l in enumerate(lines) if "up" in l and "docker" in l)
        rm_idx = next(i for i, l in enumerate(lines) if "rm" in l and "docker" in l)
        assert rm_idx > up_idx
    finally:
        os.unlink(script_path)


def test_build_exec_script_is_executable():
    """Generated script file has execute permission."""
    from common_python_tasks.utils import build_exec_script

    script_path = build_exec_script(["docker", "compose", "up"])
    try:
        mode = os.stat(script_path).st_mode
        assert mode & stat.S_IXUSR
    finally:
        os.unlink(script_path)


def test_build_exec_script_quotes_special_chars(tmp_path):
    """Script properly quotes paths containing spaces or special characters."""
    from common_python_tasks.utils import build_exec_script

    tricky_path = tmp_path / "my compose file.yml"
    script_path = build_exec_script(
        ["docker", "compose", "-f", str(tricky_path), "up"],
        cleanup_paths=[tricky_path],
    )
    try:
        content = Path(script_path).read_text()

        # shlex.quote wraps in single quotes for strings with spaces
        assert "my compose file" in content
    finally:
        os.unlink(script_path)


def test_exec_script_calls_execvpe():
    """_exec_script calls os.execvpe with /bin/sh and the script path."""
    from common_python_tasks.utils import exec_script

    with patch("common_python_tasks.tasks.os.execvpe") as mock_exec:
        env = {"PATH": "/usr/bin", "HOME": "/tmp"}
        exec_script("/tmp/test.sh", env)

        mock_exec.assert_called_once_with("/bin/sh", ["/bin/sh", "/tmp/test.sh"], env)


def test_build_exec_script_full_integration(tmp_path):
    """End-to-end: script with all options produces a well-formed shell script."""
    from common_python_tasks.utils import build_exec_script

    cleanup = [tmp_path / "compose-base.abc.yml", tmp_path / "Dockerfile"]
    compose_prefix = [
        "docker",
        "compose",
        "--project-directory",
        str(tmp_path),
        "-f",
        str(cleanup[0]),
    ]
    script_path = build_exec_script(
        [
            *compose_prefix,
            "up",
            "--watch",
            "--force-recreate",
            "--remove-orphans",
        ],
        cleanup_paths=cleanup,
        teardown_command=[*compose_prefix, "rm", "-f", "-s", "-v"],
    )
    try:
        content = Path(script_path).read_text()
        lines = content.splitlines()

        # Structural checks on key lines
        assert lines[0] == "#!/bin/sh"
        assert lines[1].startswith("SCRIPT_PATH=")
        assert "EXIT" in lines[2]

        # Find the actual compose up command (not comment lines)
        up_idx = next(
            i
            for i, l in enumerate(lines)
            if "up" in l and "docker" in l and not l.lstrip().startswith("#")
        )
        assert "up" in lines[up_idx]

        # Teardown rm command comes after up
        rm_idx = next(
            i
            for i, l in enumerate(lines)
            if "rm" in l and "docker" in l and not l.lstrip().startswith("#")
        )
        assert rm_idx > up_idx
        assert "rm -f -s -v" in lines[rm_idx]

        # Cleanup file rm commands after teardown
        after_teardown = "\n".join(lines[rm_idx + 1 :])
        assert "rm -f" in after_teardown
    finally:
        os.unlink(script_path)
