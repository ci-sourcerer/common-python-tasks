from pathlib import Path

from ._task_registry import LOGGER, tasks


def _get_ruff_command(*args: str | Path) -> list[str | Path]:
    from .project import get_ruff_target_version
    from .utils import get_ruff_config_path

    config_path, is_bundled = get_ruff_config_path()
    target_version = get_ruff_target_version() if is_bundled else None
    return [
        arg
        for arg in [
            "ruff",
            *args,
            "--config" if config_path else None,
            config_path,
            "--target-version" if target_version else None,
            target_version,
        ]
        if arg is not None
    ]


@tasks.script(tags=["test", "common"])
def test(*paths: str, quiet: bool = False) -> None:
    """Run the test suite with coverage (if pytest-cov is installed).


    Args:
        quiet: Run tests in a quieter mode.
        *paths: Optional test file paths or directories to pass through to pytest.
    """
    from .utils import (
        get_config_path,
        get_package_name,
        is_package_installed,
        run_command,
    )

    coverage_config_path = get_config_path(
        "COVERAGE_RCFILE",
        ".coveragerc",
        ".coveragerc",
        tool_name="coverage",
    )

    pytest_config_path = get_config_path(
        "PYTEST_CONFIG",
        "pytest.ini",
        "pytest.ini",
        tool_name="pytest",
    )

    if is_package_installed("pytest_cov"):
        coverage_args = [
            "--cov=" + get_package_name(use_underscores=True),
            "--cov-report=term-missing",
            "--cov-report=xml:coverage.xml",
            (
                "--cov-config=" + str(coverage_config_path)
                if coverage_config_path
                else None
            ),
        ]
    else:
        coverage_args = []

    pytest_command = [
        "pytest",
        None if quiet else "-vv",
        "-c" if pytest_config_path else None,
        str(pytest_config_path) if pytest_config_path else None,
        *coverage_args,
        *paths,
    ]
    pytest_command = [arg for arg in pytest_command if arg is not None]

    exit_code = run_command(
        pytest_command,
        acceptable_returncodes={0, 5},
    ).returncode

    if exit_code == 5:
        LOGGER.warning("No tests were collected.")

        import sys

        sys.exit(5)


@tasks.script(task_name="clean", tags=["clean", "common"])
def clean(dist_only: bool = False) -> None:
    """Clean up temporary files and directories.

    Args:
        dist_only: Only clean the dist directory (and related build artifacts)
    """
    from .utils import remove_path

    if dist_only:
        remove_path(Path("dist"))
        return
    else:
        to_clean = [
            *[
                Path(p)
                for p in [
                    ".pytest_cache",
                    "dist",
                    ".mypy_cache",
                    ".coverage",
                    "coverage.xml",
                    ".ruff_cache",
                ]
            ],
            *[
                p
                for p in Path(".").rglob("__pycache__")
                if not {".venv", "venv", "vendor", "node_modules"}.intersection(p.parts)
            ],
            *[
                p
                for p in Path(".").rglob("*.pyc")
                if not {".venv", "venv", "vendor", "node_modules"}.intersection(p.parts)
            ],
        ]

    for item in to_clean:
        remove_path(item)


@tasks.script(task_name="format", tags=["format", "common"])
def format_all() -> None:
    """Fix import issues and format Python code with Ruff."""
    from .utils import require_package, run_command

    require_package("ruff")
    run_command(
        _get_ruff_command(
            "check",
            "--fix-only",
            "--select",
            "F401,I",
            Path("."),
        )
    )
    run_command(_get_ruff_command("format", Path(".")))


@tasks.script(task_name="lint", tags=["lint", "common"])
def lint_all() -> None:
    """Check Python lint and formatting with Ruff."""
    from .utils import require_package, run_command

    require_package("ruff")
    run_command(_get_ruff_command("check", Path(".")))
    run_command(_get_ruff_command("format", "--check", Path(".")))


@tasks.script(task_name="docs-build", tags=["docs"])
def docs_build(config_file: str | None = None, clean: bool = False) -> None:
    """Build the Zensical documentation site in strict mode.

    Args:
        config_file: Optional path to a Zensical configuration file.
        clean: Remove cached files before building the site.
    """
    from .utils import require_package, run_command

    require_package("zensical")
    run_command(
        [
            "zensical",
            "build",
            "--strict",
            "--clean" if clean else None,
            "--config-file" if config_file else None,
            config_file,
        ]
    )


@tasks.script(task_name="docs-serve", tags=["docs"])
def docs_serve(
    config_file: str | None = None,
    dev_addr: str | None = None,
    open_browser: bool = False,
) -> None:
    """Serve the Zensical documentation site for local preview.

    Args:
        config_file: Optional path to a Zensical configuration file.
        dev_addr: Optional development server address in `IP:PORT` form.
        open_browser: Open the preview in the default browser.
    """
    from .utils import require_package, run_command

    require_package("zensical")
    run_command(
        [
            "zensical",
            "serve",
            "--config-file" if config_file else None,
            config_file,
            "--dev-addr" if dev_addr else None,
            dev_addr,
            "--open" if open_browser else None,
        ]
    )
