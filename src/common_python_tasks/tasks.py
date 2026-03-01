import logging
import os
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Literal, Any, Callable, Sequence

from poethepoet_tasks import TaskCollection


class _ColoredFormatter(logging.Formatter):
    COLORS = {
        "WARNING": "\033[93m",
        "ERROR": "\033[91m",
        "CRITICAL": "\033[91m",
        "RESET": "\033[0m",
    }

    def format(self, record: logging.LogRecord) -> str:
        log_color = self.COLORS.get(record.levelname, "")
        record.levelname = f"\033[1m{log_color}{record.levelname}{self.COLORS['RESET'] if log_color else ''}\033[0m"
        return super().format(record)


LOGGER = logging.getLogger("common_python_tasks")
handler = logging.StreamHandler()
handler.setFormatter(_ColoredFormatter("[%(asctime)s] %(levelname)s: %(message)s"))
LOGGER.addHandler(handler)
LOGGER.setLevel(
    {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }[os.getenv("COMMON_PYTHON_TASKS_LOG_LEVEL", "INFO").upper()]
)


def _env_truthy(env_var: str) -> bool:
    """Return `True` if the environment variable is set to a truthy value."""
    return os.getenv(env_var, "").lower() in {
        "1",
        "true",
        "yes",
        "on",
        "enabled",
        "y",
        "t",
    }


@lru_cache
def _is_package_installed(package_name: str) -> bool:
    from importlib.util import find_spec

    is_installed = find_spec(package_name.replace("-", "_")) is not None
    if not is_installed:
        LOGGER.debug("%s is not installed", package_name)

    return is_installed


def _fatal(message: str, exit_code: int = 1) -> None:
    import sys

    LOGGER.critical(message)
    sys.exit(exit_code)


def _require_package(package_name: str) -> None:
    if not _is_package_installed(package_name):
        _fatal(f"{package_name} is not installed")


def _run_available_tools(
    tools: list[tuple[Callable, str]], none_available_message: str
) -> None:
    ran_any = False
    for fn, package in tools:
        if _is_package_installed(package):
            fn()
            ran_any = True
    if not ran_any:
        _fatal(none_available_message)


def _get_authors() -> list[tuple[str, str]]:
    import tomllib

    return [
        ((a.get("name") or "").strip(), (a.get("email") or "").strip().strip("<>"))
        for a in tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
        .get("project", {})
        .get("authors", [])
    ]


def _run_command(
    command: Sequence[str],
    *,
    capture_output: bool = False,
    acceptable_returncodes: Sequence[int] | None = None,
    env: dict[str, str] | None = None,
) -> "subprocess.CompletedProcess":
    import subprocess
    from shlex import quote

    if acceptable_returncodes is None:
        acceptable_returncodes = {0}

    command = [str(c) for c in command if c is not None]

    bold_command_display = (
        f"\033[1m{" ".join([quote(str(arg)) for arg in command])}\033[0m"
    )
    LOGGER.debug("Running command: %s", bold_command_display)

    merged_env = {**os.environ, **env} if env is not None else None

    out = subprocess.run(
        command, capture_output=capture_output, text=True, env=merged_env
    )
    if out.returncode not in acceptable_returncodes:
        if capture_output:
            stdout = out.stdout.strip() if out.stdout else ""
            stderr = out.stderr.strip() if out.stderr else ""
            details = ""
            if stdout:
                details += f"\nstdout: {stdout}"
            if stderr:
                details += f"\nstderr: {stderr}"
        else:
            details = ""
        LOGGER.critical(
            "Command failed (exit code %d): %s%s",
            out.returncode,
            bold_command_display,
            details,
        )

        import sys

        sys.exit(out.returncode)
    return out


def _load_data_file(
    file_name: str, type_identifier: str = "generic", fatal_on_missing: bool = True
) -> tuple[str, str] | None:
    from importlib.resources import files

    try:
        data_files = files("common_python_tasks") / "data" / type_identifier
        data_file = data_files / file_name
        return (str(data_file), data_file.read_text())
    except FileNotFoundError as e:
        if fatal_on_missing:
            _fatal(f"Data file not found: {file_name} ({e})")
        return None


def _get_dirty_files(ignore: list[str] | None = None) -> list[str]:
    if ignore is None:
        ignore = []

    return [
        f
        for f in [
            line[3:]
            for line in _run_command(
                ["git", "status", "--porcelain"], capture_output=True
            ).stdout.splitlines()
            if line
        ]
        if f not in ignore
    ]


def _get_version(files_to_ignore_as_dirty: list[str] | None = None) -> str:
    from dunamai import Style, Version

    if files_to_ignore_as_dirty is None:
        files_to_ignore_as_dirty = []

    dirty_files = _get_dirty_files(ignore=files_to_ignore_as_dirty)
    LOGGER.debug("Dirty files: %s", dirty_files)

    return Version.from_git().serialize(
        style=Style.Pep440,
        dirty=bool(dirty_files),
    )


def _get_image_tag(files_to_ignore_as_dirty: list[str] | None = None) -> str:
    if files_to_ignore_as_dirty is None:
        files_to_ignore_as_dirty = []

    return (
        _get_version(files_to_ignore_as_dirty=files_to_ignore_as_dirty)
        .replace(".post", "-post")
        .replace(".dev", "-dev")
        .replace("+", "-")
    )


def _has_tags_later_in_history() -> bool:
    result = _run_command(
        ["git", "tag"],
        capture_output=True,
        acceptable_returncodes={0, 128},
    )
    if result.returncode != 0 or not result.stdout.strip():
        return False

    for tag in result.stdout.strip().split("\n"):
        check_result = _run_command(
            ["git", "merge-base", "--is-ancestor", "HEAD", tag],
            capture_output=True,
            acceptable_returncodes={0, 1},
        )
        if check_result.returncode == 1:
            return True

    return False


def _get_dockerhub_username() -> str:
    from getpass import getuser

    return os.getenv("DOCKERHUB_USERNAME") or getuser()


def _get_registry_url() -> str:
    return os.environ.get(
        "CONTAINER_REGISTRY_URL",
        f"docker.io/{_get_dockerhub_username()}",
    ).strip()


def _get_full_image_name() -> str:
    return f"{_get_registry_url()}/{_get_package_name()}"


def _get_package_name(use_underscores: bool = False) -> str:
    import tomllib

    name = os.getenv("PACKAGE_NAME") or tomllib.loads(
        Path("pyproject.toml").read_text()
    ).get("project", {}).get("name")
    if use_underscores and name:
        name = name.replace("-", "_")
    return name


def _get_poetry_version() -> str:
    return (
        _run_command(["poetry", "--version"], capture_output=True)
        .stdout.strip()
        .split()[-1]
    )[0:-1]


@lru_cache
def _read_pyproject_toml() -> dict[str, Any]:
    import tomllib

    return tomllib.loads(Path("pyproject.toml").read_text())


def get_config_path(
    env_var_name: str,
    local_config_filename: str,
    data_config_filename: str,
    *,
    tool_name: str | None = None,
    type_identifier: str = "generic",
) -> Path | None:
    """Get the path to a configuration file.

    Checks for configuration in the following order:
    1. If tool_name provided, check if `tool.{tool_name}` exists in `pyproject.toml`
       - If it exists, return `None` (use `pyproject.toml` config)
    2. Check environment variable
    3. Check for local config file
    4. Fall back to bundled data file

    Args:
        env_var_name: Name of the environment variable to check.
        local_config_filename: Name of the local config file to look for.
        data_config_filename: Name of the bundled config file to use as fallback.
        tool_name: Optional tool name to check in `pyproject.toml` under `[tool.{tool_name}]`.

    Returns:
        `Path` to config file, or `None` if config exists in `pyproject.toml`
    """
    if tool_name is not None:
        pyproject_data = _read_pyproject_toml()
        if pyproject_data.get("tool", {}).get(tool_name):
            LOGGER.debug("Using [tool.%s] configuration from pyproject.toml", tool_name)
            return None

    if os.getenv(env_var_name):
        config_path = Path(os.getenv(env_var_name))
        LOGGER.debug("Using config from %s: %s", env_var_name, config_path)
        return config_path

    local_config_path = Path(local_config_filename)
    if local_config_path.exists():
        LOGGER.debug("Using local config file: %s", local_config_path)
        return local_config_path

    config_path = Path(
        _load_data_file(data_config_filename, type_identifier=type_identifier)[0]
    )
    LOGGER.debug("Using bundled config file: %s", config_path)
    return config_path


tasks = TaskCollection(
    envfile=[
        f
        for f in [
            ".env.defaults",
            "project.properties",
            ".env",
        ]
        if Path(f).exists()
    ]
)


@tasks.script(task_name="_black", tags=["format", "internal"])
def black() -> None:
    """Run black formatting."""
    _require_package("black")
    _run_command(["black", "--quiet", "."])


@tasks.script(task_name="_isort", tags=["format", "internal"])
def isort() -> None:
    """Run isort formatting."""
    _require_package("isort")
    isort_config_path = get_config_path(
        "ISORT_CONFIG",
        ".isort.cfg",
        ".isort.cfg",
        tool_name="isort",
    )

    _run_command(
        [
            "isort",
            "--quiet",
            ".",
            "--settings-path",
            isort_config_path,
        ]
    )


@tasks.script(task_name="_autoflake", tags=["format", "internal"])
def autoflake() -> None:
    """Run autoflake to remove unused imports."""
    _require_package("autoflake")
    _run_command(
        [
            "autoflake",
            "--quiet",
            "--remove-all-unused-imports",
            "--recursive",
            "-i",
            Path("."),
        ]
    )


@tasks.script(task_name="_black_check", tags=["lint", "internal"])
def black_check() -> None:
    """Run black in check mode."""
    _require_package("black")
    _run_command(["black", "--quiet", "--diff", Path("."), "--check"])


@tasks.script(task_name="_isort_check", tags=["lint"])
def isort_check() -> None:
    """Run isort linting."""
    _require_package("isort")
    isort_config_path = get_config_path(
        "ISORT_CONFIG",
        ".isort.cfg",
        ".isort.cfg",
        tool_name="isort",
    )

    _run_command(
        [
            "isort",
            "--quiet",
            ".",
            "--check-only",
            "--settings-path",
            isort_config_path,
        ]
    )


@tasks.script(task_name="_autoflake_check", tags=["lint", "internal"])
def autoflake_check() -> None:
    """Run autoflake in check mode."""
    _require_package("autoflake")
    _run_command(
        [
            "autoflake",
            "--quiet",
            "--remove-all-unused-imports",
            "--recursive",
            "-cd",
            Path("."),
        ]
    )


@tasks.script(task_name="_flake8_check", tags=["lint"])
def flake8_check() -> None:
    """Run flake8 linting."""
    _require_package("flake8")

    flake8_config_path = get_config_path("FLAKE8_CONFIG", ".flake8", ".flake8")

    _run_command(["flake8", Path("."), "--config", flake8_config_path])


@tasks.script(tags=["test"])
def test(quiet: bool = False) -> None:
    """Run the test suite with coverage (if `pytest-cov` is installed).


    Args:
        quiet: If `True`, run tests in a quieter mode.
    """
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

    if _is_package_installed("pytest_cov"):
        coverage_args = [
            "--cov=" + _get_package_name(use_underscores=True),
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

    exit_code = _run_command(
        [
            "pytest",
            None if quiet else "-vv",
            "-c" if pytest_config_path else None,
            str(pytest_config_path) if pytest_config_path else None,
            *coverage_args,
        ],
        acceptable_returncodes={0, 5},
    ).returncode

    if exit_code == 5:
        LOGGER.warning("No tests were collected.")

        import sys

        sys.exit(5)


@tasks.script(task_name="clean", tags=["clean"])
def clean() -> None:
    """Clean up temporary files and directories."""
    import shutil

    for item in [
        *[Path(p) for p in [".pytest_cache", "dist", ".mypy_cache"]],
        *Path(".").rglob("__pycache__"),
        *Path(".").rglob("*.pyc"),
        Path(".coverage"),
        Path("coverage.xml"),
    ]:
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            item.unlink(missing_ok=True)


@tasks.script(task_name="format", tags=["format"])
def format_all() -> None:
    """Format Python code with autoflake, black, and isort."""
    _run_available_tools(
        [
            (autoflake, "autoflake"),
            (black, "black"),
            (isort, "isort"),
        ],
        "No formatting tools are installed. Install one or more of: autoflake, black, isort",
    )


@tasks.script(task_name="lint", tags=["lint"])
def lint_all() -> None:
    """Lint Python code with autoflake, black, isort, and flake8."""
    _run_available_tools(
        [
            (autoflake_check, "autoflake"),
            (black_check, "black"),
            (isort_check, "isort"),
            (flake8_check, "flake8"),
        ],
        "No linting tools are installed. Install one or more of: autoflake, black, isort, flake8",
    )


def _build_image(
    containerfile_path: Path | None = None,
    containerfile_text: str | None = None,
    context_path: Path | None = None,
    debug: bool = False,
    no_cache: bool = False,
    plain: bool = False,
    single_arch: bool = False,
    omit_target: bool = False,
    image_name: str | None = None,
    extra_build_args: dict[str, str] | None = None,
) -> tuple[str, str]:
    import platform

    dist_path = Path("dist")
    if dist_path.exists() and any(dist_path.iterdir()):
        LOGGER.warning(
            "The 'dist' directory is not empty. "
            "This may indicate that old build artifacts are present which could be "
            "unintentionally included in the image build context or cause the image "
            "build to fail. Consider cleaning the 'dist' directory before building "
            "with `poe clean`."
        )

    if context_path is None:
        context_path = Path(".")

    temp_file_path: str | None = None
    if containerfile_path is None:
        if containerfile_text is None:
            _fatal("Either containerfile_path or containerfile_text must be provided.")
        import tempfile

        tf = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            prefix="Containerfile.",
            suffix=".generated",
        )
        temp_file_path = tf.name
        with open(temp_file_path, "w", encoding="utf-8") as f:
            f.write(containerfile_text)
        containerfile_path = Path(temp_file_path)

    dockerignore_path = context_path / ".dockerignore"
    temp_dockerignore_created = False
    if not dockerignore_path.exists():
        LOGGER.debug("No .dockerignore found, using built-in .dockerignore")
        builtin_dockerignore_content = _load_data_file(".dockerignore")[1]
        dockerignore_path.write_text(builtin_dockerignore_content, encoding="utf-8")
        temp_dockerignore_created = True

    delete_temp_file = False
    try:
        # TODO: Revisit this in regards to more architectures
        archs = ["linux/amd64", "linux/arm64"] if not single_arch else None
        files_to_ignore = [".dockerignore"] if temp_dockerignore_created else []
        version_string = _get_image_tag(files_to_ignore_as_dirty=files_to_ignore)

        if debug:
            suffix = "-debug"
            target = "debug"
            tag = "debug"
        else:
            suffix = ""
            target = "runtime"
            # Only tag as 'latest' if there are no tags later in history
            tag = "latest" if not _has_tags_later_in_history() else None

        version_tag = f"{version_string}{suffix}"
        commit_tag = f"{_run_command(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True).stdout.strip()}{'-dirty' if _get_dirty_files(ignore=files_to_ignore) else ''}{suffix}"
        python_version = platform.python_version()
        poetry_version = _get_poetry_version()

        build_args = {
            k: v
            for k, v in {
                "PYTHON_VERSION": python_version,
                "POETRY_VERSION": poetry_version,
                "PACKAGE_NAME": _get_package_name(use_underscores=True),
                "AUTHORS": ",".join(
                    [f"{name} <{email}>" for name, email in _get_authors()]
                ),
                "GIT_COMMIT": commit_tag,
                "CUSTOM_ENTRYPOINT": os.getenv("CUSTOM_IMAGE_ENTRYPOINT"),
            }.items()
            if v is not None
        }
        # Merge in caller-supplied build-args (used by extension builds)
        if extra_build_args:
            for k, v in extra_build_args.items():
                if v is not None:
                    build_args[k] = v
        tags_to_use = [t for t in (tag, version_tag, commit_tag) if t is not None]
        LOGGER.debug("Building image with tags: %s", ", ".join(tags_to_use))
        # Allow override of image name for extension builds
        image_short_name = image_name if image_name is not None else _get_package_name()
        orig_full_name = _get_full_image_name()
        if image_name is None:
            image_full_name = orig_full_name
        else:
            if "/" in orig_full_name:
                prefix = orig_full_name.rsplit("/", 1)[0]
                image_full_name = f"{prefix}/{image_name}"
            else:
                image_full_name = image_name
        build_cmd = [
            "docker",
            "build",
            str(context_path),
            "-f",
            str(containerfile_path),
            "--target" if not omit_target else None,
            target if not omit_target else None,
            *[
                item
                for k, v in build_args.items()
                for item in ("--build-arg", f"{k}={v if v is not None else ''}")
            ],
            "--platform" if archs else None,
            ",".join(archs) if archs else None,
            "--no-cache" if no_cache else None,
            *[item for t in tags_to_use for item in ("-t", f"{image_short_name}:{t}")],
        ]
        for t in tags_to_use:
            build_cmd += ["-t", f"{image_full_name}:{t}"]

        if plain:
            build_cmd += ["--progress", "plain"]
        _run_command(build_cmd)
        delete_temp_file = True
    finally:
        if temp_file_path is not None and delete_temp_file:
            try:
                containerfile_path.unlink()
            except FileNotFoundError:
                pass
        if temp_dockerignore_created:
            try:
                dockerignore_path.unlink()
            except FileNotFoundError:
                pass
    return version_tag, commit_tag


def _parse_container_extensions() -> list[dict]:
    """Parse CONTAINER_EXTENSION_FILES and CONTAINER_EXTENSIONS (colon-delimited).
    Returns a list of descriptors: {id, source, path, bundle_name} in order.
    """
    exts: list[dict] = []
    files_raw = os.getenv("CONTAINER_EXTENSION_FILES")
    if files_raw:
        for part in [p.strip() for p in files_raw.split(":") if p.strip()]:
            # Derive id from filename where possible
            pth = Path(part)
            exts.append(
                {
                    "id": (
                        pth.name.split("Containerfile.", 1)[1]
                        if pth.name.startswith("Containerfile.")
                        else pth.stem
                    ),
                    "source": "file",
                    "path": part,
                    "bundle_name": None,
                }
            )
    bundles_raw = os.getenv("CONTAINER_EXTENSIONS")
    if bundles_raw:
        for part in (p.strip() for p in bundles_raw.split(":")):
            if not part:
                continue
            # Support parameterised extensions: name=arg1 arg2 ...
            if "=" in part:
                name, _, args = part.partition("=")
                name = name.strip()
                args = args.strip()
            else:
                name = part
                args = None
            exts.append(
                {
                    "id": name,
                    "source": "bundle",
                    "path": None,
                    "bundle_name": name,
                    "args": args,
                }
            )
    return exts


def _resolve_extension_content(descriptor: dict[str, str | None]) -> str:
    """Return the Containerfile fragment for the given descriptor.

    This helper fails fast (calls `_fatal`) when an expected file/bundle is
    missing so callers can validate all extensions up-front without duplicating
    existence checks.
    """
    if descriptor["source"] == "file":
        p = Path(descriptor["path"] or "")
        if not p.exists():
            _fatal(f"Extension Containerfile not found: {p}")
        return p.read_text(encoding="utf-8")
    if descriptor["source"] == "bundle":
        bundle_name = descriptor["bundle_name"]
        out = _load_data_file(
            f"{bundle_name}/Containerfile",
            type_identifier="containerfile_extensions",
            fatal_on_missing=False,
        )
        if out is None:
            _fatal(f"Extension bundle not found: {bundle_name}")
        return out[1]
    _fatal(f"Unknown extension descriptor source: {descriptor['source']}")


def _build_extension_image(
    base_full_name: str,
    base_version_tag: str,
    extension_content: str,
    context_path: Path | None = None,
    image_name_override: str | None = None,
    debug: bool = False,
    no_cache: bool = False,
    single_arch: bool = False,
    extra_build_args: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Build an image that starts `FROM` the primary image and returns its tags.

    The created Containerfile will begin with `FROM {base_full_name}:{base_version_tag}`
    followed by the provided extension content.
    """
    if context_path is None:
        context_path = Path(".")

    LOGGER.debug(
        "Building extension image based on %s:%s with override name '%s'",
        base_full_name,
        base_version_tag,
        image_name_override,
    )
    return _build_image(
        None,
        f"FROM {base_full_name}:{base_version_tag}\n\n{extension_content}\n",
        context_path,
        debug=debug,
        no_cache=no_cache,
        plain=False,
        single_arch=single_arch,
        omit_target=True,
        image_name=image_name_override or _get_package_name(),
        extra_build_args=extra_build_args,
    )


def _get_prune_keep() -> int:
    """Return the integer value of CONTAINER_PRUNE_KEEP.

    Semantics:
      -1 => keep all (no pruning)
       0 => keep only the latest
       N => keep latest + N previous
    Defaults to -1 when unset or invalid.
    """
    raw = os.getenv("CONTAINER_PRUNE_KEEP")
    if raw is None:
        return -1
    try:
        return int(raw)
    except Exception:
        LOGGER.warning(
            "Invalid CONTAINER_PRUNE_KEEP value '%s' - defaulting to -1 (no prune)", raw
        )
        return -1


def _prune_images_keep(
    full_name: str, package_name: str, keep: int, protect_tags: list[str] | None = None
) -> None:
    """Prune images for `full_name` keeping the most-recent `keep + 1` images.

    - `keep` follows CONTAINER_PRUNE_KEEP semantics: -1 => do nothing.
    - `protect_tags` are never removed even if older.
    """
    if keep < 0:
        return
    if protect_tags is None:
        protect_tags = []

    retain_count = keep + 1

    res = _run_command(
        [
            "docker",
            "image",
            "ls",
            "--format",
            "{{.Repository}}:{{.Tag}}",
            "--filter",
            f"reference={full_name}:*",
        ],
        capture_output=True,
        acceptable_returncodes={0, 1},
    )
    if res.returncode != 0:
        LOGGER.exception("Failed to list images for pruning: %s", full_name)
        return

    lines = [
        line.strip()
        for line in res.stdout.splitlines()
        if line.strip() and not line.strip().startswith("<none>")
    ]
    tags_in_order: list[str] = []
    for entry in lines:
        if ":" not in entry:
            continue
        repo, tag = entry.rsplit(":", 1)
        # Only consider entries that match the full_name (ignore other repos)
        # repo may be like docker.io/username/test-package
        if entry.startswith(full_name) or repo.endswith(package_name):
            tags_in_order.append(tag)

    candidates = [t for t in tags_in_order if t not in protect_tags]
    if len(candidates) <= retain_count:
        return

    to_delete = candidates[retain_count:]
    for tag in to_delete:
        for img in (f"{package_name}:{tag}", f"{full_name}:{tag}"):
            try:
                LOGGER.info("Pruning image %s", img)
                _run_command(["docker", "rmi", img], acceptable_returncodes={0, 1})
            except SystemExit:
                LOGGER.warning(
                    "Failed to remove image %s during pruning; continuing", img
                )


@tasks.script(tags=["containers", "build"])
def build_image(
    debug: bool = False,
    no_cache: bool = False,
    plain: bool = False,
    single_arch: bool = False,
    build_args: str | None = None,
) -> None:
    """Build the container image for this project using the Containerfile template.

    Args:
        debug: Build the debug image.
        no_cache: Do not use cache when building the image.
        plain: Do not pretty-print output.
        single_arch: Build images for a single architecture.
        build_args: Additional build arguments (format: "KEY=VAL:OTHER=VAL"). Overrides CONTAINER_BUILD_ARGS env var if provided.
    """
    # Determine extensions up-front so we can log a single, accurate message
    extensions = _parse_container_extensions()
    extension_ids = [desc.get("id") for desc in extensions if desc.get("id")]
    if extension_ids:
        LOGGER.info("Building image (with extensions: %s)", ", ".join(extension_ids))
    else:
        LOGGER.info("Building image")

    # Resolve all extension fragments up-front so we fail fast on missing
    # bundles or files and avoid calling resolution logic multiple times.
    resolved_fragments = [_resolve_extension_content(desc) for desc in extensions]

    # Parse build-args (CLI param overrides environment). Format: "KEY=VAL:OTHER=VAL"
    raw_build_args = (
        build_args if build_args is not None else os.getenv("CONTAINER_BUILD_ARGS")
    )
    parsed_build_args: dict[str, str] | None = None
    if raw_build_args:
        parsed_build_args = {}
        for part in (p.strip() for p in raw_build_args.split(":") if p.strip()):
            if "=" in part:
                k, v = part.split("=", 1)
                parsed_build_args[k.strip()] = v.strip()
            else:
                LOGGER.warning("Ignoring invalid build-arg token: %s", part)

    version_tag, commit_tag = _build_image(
        None,
        _load_data_file("Containerfile")[1],
        Path("."),
        debug=debug,
        no_cache=no_cache,
        plain=plain,
        single_arch=single_arch,
        extra_build_args=parsed_build_args,
    )

    if extensions:
        combined_content = "\n\n".join(
            c for c in [f.rstrip() for f in resolved_fragments] if c
        )
        # Collect extension-specific build-args (convention per-bundle)
        extra_build_args: dict[str, str] = {}
        import re

        for desc, fragment in zip(extensions, resolved_fragments):
            args_val = desc.get("args")
            if args_val is None:
                continue

            arg_names = re.findall(
                r"^\s*ARG\s+([A-Za-z_][A-Za-z0-9_]*)", fragment, re.M
            )
            if not arg_names:
                LOGGER.warning(
                    "Extension '%s' provided arguments but its Containerfile contains no ARG declaration — arguments ignored",
                    desc.get("id", "?"),
                )
                continue

            # Use the first ARG that isn't already set by another extension
            for arg_name in arg_names:
                if arg_name not in extra_build_args:
                    extra_build_args[arg_name] = args_val or ""
                    break

        # Merge top-level build-args with any extension-specific build-args
        merged_build_args = {**(parsed_build_args or {})}
        merged_build_args.update(extra_build_args or {})

        _build_extension_image(
            _get_full_image_name(),
            version_tag,
            combined_content,
            context_path=Path("."),
            debug=debug,
            no_cache=no_cache,
            single_arch=single_arch,
            extra_build_args=merged_build_args or None,
        )

    keep = _get_prune_keep()
    if keep >= 0:
        # Protect the tags created by this build
        protect = [t for t in (version_tag, commit_tag) if t is not None]
        LOGGER.debug(
            "Pruning old images; keeping %d and protecting tags: %s", keep, protect
        )
        _prune_images_keep(
            _get_full_image_name(), _get_package_name(), keep, protect_tags=protect
        )


@tasks.script(tags=["containers"])
def run_container(
    tag: str | None = None,
    *,
    entrypoint: str | None = None,
    command: str | None = None,
    root: bool = False,
    echo_env: bool = False,
) -> None:
    """Run the Docker image as a container for this project.

    By default (when `tag` is `None`) this will run the most-recently-built tag for
    the project's image.

    Args:
        tag: Image tag to run. If `None`, use the most-recently-built tag.
        entrypoint: Optional entrypoint override.
        command: Optional command to pass to the entrypoint.
        root: Whether to run as root (only relevant with a shell entrypoint).
        echo_env: Whether to prepend an env dump to the command.
    """
    package_name = _get_package_name()
    if not package_name:
        _fatal("PACKAGE_NAME could not be resolved")

    full_name = _get_full_image_name()
    selected_image: str | None = None

    def _image_exists(image: str) -> bool:
        res = _run_command(
            ["docker", "image", "inspect", image],
            capture_output=True,
            acceptable_returncodes={0, 1},
        )
        return res.returncode == 0

    if tag:
        # Prefer short name, fall back to full name if necessary
        for candidate in (f"{package_name}:{tag}", f"{full_name}:{tag}"):
            if _image_exists(candidate):
                selected_image = candidate
                break
        if selected_image is None:
            # Not found locally — assume full name (allow docker to pull if needed)
            selected_image = f"{full_name}:{tag}"
    else:
        # Find the most-recently-built tag (newest first) for the image
        for repo in (full_name, package_name):
            res = _run_command(
                [
                    "docker",
                    "image",
                    "ls",
                    "--format",
                    "{{.Repository}}:{{.Tag}}",
                    "--filter",
                    f"reference={repo}:*",
                ],
                capture_output=True,
                acceptable_returncodes={0, 1},
            )
            if res.returncode == 0 and res.stdout.strip():
                matched_line = next(
                    (
                        line
                        for line in res.stdout.splitlines()
                        if line.strip() and not line.strip().startswith("<none>")
                    ),
                    None,
                )
                if matched_line:
                    selected_image = matched_line.strip()
                    break
        if selected_image is None:
            _fatal(
                f"No local images found for {package_name}. Build the image first or specify a tag."
            )

    LOGGER.info("Running container %s", selected_image)
    _run_command(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "-t",
            "--entrypoint" if entrypoint else None,
            entrypoint,
            "--user" if root else None,
            "root" if root else None,
            selected_image,
            "-c" if command else None,
            (
                (
                    "echo '=== Container Environment Variables ===' && env && echo '===================================' && exec "
                    + command
                )
                if echo_env and command
                else command
            ),
        ]
    )


@tasks.script(tags=["containers", "packaging", "release"])
def push_image(debug: bool = False) -> None:
    """Push the Docker image for this project to the container registry.

    Args:
        debug: Push the debug image.
    """

    if debug:
        suffix = "-debug"
        tag = "debug"
    else:
        suffix = ""
        # Only push 'latest' tag if there are no tags later in history
        tag = "latest" if not _has_tags_later_in_history() else None
    full_name = _get_full_image_name()
    tags_to_push = [t for t in [tag, f"{_get_image_tag()}{suffix}"] if t is not None]
    for t in tags_to_push:
        full_tag = f"{full_name}:{t}"
        LOGGER.info("Pushing image %s", full_tag)
        _run_command(["docker", "push", full_tag])


@tasks.script(task_name="publish-package", tags=["packaging"])
def publish_package() -> None:
    """Publish the package to the PyPI server."""
    _run_command(["poetry", "publish"])


@tasks.script(task_name="build-package", tags=["packaging", "build"])
def build_package(wheel_only: bool = False) -> None:
    """Build the package (wheel and sdist)."""
    command = ["poetry", "build"]
    if wheel_only:
        command += ["--format", "wheel"]
    _run_command(command)


@tasks.script(tags=["packaging"])
def bump_version(
    component: str = "patch",
    *,
    stage: str | None = None,
    dry_run: bool = False,
) -> None:
    """Bump the project version.

    Args:
        component: The version component to bump: `major`, `minor`, or `patch`.
        stage: Optional pre-release stage to apply: `alpha`, `beta`, or `rc`.
        dry_run: If `True`, print what would happen without making changes.
    """
    from dunamai import Version

    component = component.lower()
    stage = stage.lower() if stage is not None else None

    valid_components = {"major": 0, "minor": 1, "patch": 2}
    if component not in valid_components:
        _fatal(f'Invalid component "{component}". Must be one of: major, minor, patch')
    bump_index: "Literal[0, 1, 2]" = valid_components[component]

    if stage is not None and stage not in {"alpha", "a", "beta", "b", "rc"}:
        _fatal(f'Invalid stage "{stage}". Must be one of: alpha, beta, rc')

    if _get_dirty_files():
        _fatal(
            "Repository has uncommitted changes. "
            "Please commit or stash changes before bumping version."
        )

    tag_result = _run_command(
        ["git", "describe", "--tags", "--abbrev=0"],
        capture_output=True,
        acceptable_returncodes={0, 128},
    )

    if tag_result.returncode == 0 and tag_result.stdout.strip():
        version_str = tag_result.stdout.strip().lstrip("v")
    else:
        version_str = "0.0.0"

    bumped = Version.parse(version_str).bump(bump_index)

    if stage is not None:
        bumped.stage = {"a": "alpha", "b": "beta"}.get(stage, stage)
        bumped.revision = 1

    new_version = bumped.serialize()

    if dry_run:
        LOGGER.info("Dry run: would bump version to %s", new_version)
    else:
        new_tag = f"v{new_version}"
        LOGGER.info("Bumping version to %s", new_version)
        _run_command(["git", "tag", new_tag])


def _build(
    has_containers: bool,
    debug: bool = False,
    no_cache: bool = False,
    plain: bool = False,
    single_arch: bool = False,
) -> None:
    build_package()
    if has_containers:
        build_image(
            debug=debug,
            no_cache=no_cache,
            plain=plain,
            single_arch=single_arch,
        )


@tasks.script(
    task_name="build",
    tags=["packaging", "containers"],
)
def build_with_containers(
    debug: bool = False,
    no_cache: bool = False,
    plain: bool = False,
    single_arch: bool = False,
) -> None:
    """Build the project and its containers.

    Args:
        debug: Build the debug image.
        no_cache: Do not use cache when building the image.
        plain: Do not pretty-print output.
        single_arch: Build images for a single architecture.
    """
    _build(
        True,
        debug=debug,
        no_cache=no_cache,
        plain=plain,
        single_arch=single_arch,
    )


@tasks.script(task_name="build", tags=["packaging"])
def build_without_containers() -> None:
    """Build the project."""
    _build(False)


def _ensure_alembic_config(compose_type: str) -> tuple[Path | None, bool]:
    """Render `alembic.ini` from the bundled template when a local copy is absent.

    Returns `(path, should_cleanup)`.
    """
    alembic_ini_path = Path("alembic.ini")
    if alembic_ini_path.exists():
        LOGGER.debug("Using existing alembic.ini")
        return alembic_ini_path, False

    result = _load_data_file(
        "alembic.ini.j2", type_identifier=compose_type, fatal_on_missing=False
    )
    if result is None:
        return None, False

    from jinja2 import Template

    _, template_content = result
    rendered = Template(template_content).render(
        package_name=_get_package_name(use_underscores=True),
    )
    alembic_ini_path.write_text(rendered, encoding="utf-8")
    LOGGER.debug("Rendered bundled alembic.ini.j2 to %s", alembic_ini_path)
    return alembic_ini_path, True


def _resolve_compose_file(
    env_var_name: str,
    local_filename: str,
    data_filename: str,
    *,
    render_template: bool = False,
    type_identifier: str = "generic",
    extra_template_vars: dict[str, str] | None = None,
) -> tuple[str, bool]:
    """Resolve a compose file path with env/local/data precedence.

    Returns the usable path and whether it should be cleaned up (temp file).
    """
    import tempfile

    resolved_path = get_config_path(
        env_var_name,
        local_filename,
        data_filename,
        type_identifier=type_identifier,
    )
    if resolved_path is None:
        _fatal(f"No compose configuration resolved for {data_filename}")

    path_obj = Path(resolved_path)
    should_template = render_template or path_obj.suffix == ".j2"

    if should_template:
        from jinja2 import Template

        package_name = _get_package_name()
        env_prefix = os.getenv(
            "ENV_PREFIX",
            package_name.upper().replace("-", "_") if package_name else "",
        )
        template_vars = {
            "PACKAGE_NAME": package_name,
            "PACKAGE_UNDERSCORE_NAME": (
                package_name.replace("-", "_") if package_name else ""
            ),
            "ENV_PREFIX": env_prefix,
        }
        if extra_template_vars:
            template_vars.update(extra_template_vars)
        rendered = Template(path_obj.read_text()).render(**template_vars)
        tf = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            prefix=path_obj.stem + ".",
            suffix=".yml",
        )
        temp_path = tf.name
        tf.write(rendered)
        tf.close()
        return temp_path, True

    return str(path_obj), False


def _read_dotenv(path: Path) -> dict[str, str]:
    """Parse a simple `.env` file into a `dict` (`KEY=VALUE`, ignore comments)."""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                env[key] = value
    except Exception as exc:
        LOGGER.debug("Failed to parse .env file %s: %s", path, exc)
    return env


def _append_dotenv(path: Path, items: dict[str, str]) -> None:
    """Append key/value pairs to `.env` with a generated header comment."""
    from datetime import datetime

    header = f"\n# Auto-generated by common_python_tasks on {datetime.now().isoformat(timespec='seconds')}\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(header)
        for k, v in items.items():
            f.write(f"{k}={v}\n")


def _get_or_generate_secret(key_name: str, *, length_bytes: int = 32) -> str:
    """Get an env var or generate, store in `.env`, and return it.

    - Respects already-set environment variables
    - If not set, checks `.env` for an existing value
    - Otherwise generates with `secrets.token_hex(length_bytes)`, appends to `.env`,
      logs at `INFO`, and returns the value
    """
    import secrets

    existing = os.getenv(key_name)
    if existing:
        return existing

    dotenv_path = Path(".env")
    existing_in_file = _read_dotenv(dotenv_path).get(key_name)
    if existing_in_file:
        os.environ[key_name] = existing_in_file
        return existing_in_file

    token = secrets.token_hex(length_bytes)
    try:
        _append_dotenv(dotenv_path, {key_name: token})
        LOGGER.info("Generated %s and stored it in .env", key_name)
    except Exception as exc:
        LOGGER.warning(
            "Failed to persist %s to .env (%s); using in-memory only", key_name, exc
        )
    os.environ[key_name] = token
    return token


def _ensure_secrets_generated() -> None:
    """Ensure required secrets exist (generate once and persist to .env)."""
    _get_or_generate_secret("SECRET_KEY")
    _get_or_generate_secret("DB_PASS")


_COMPOSE_VAR_REQUIREMENTS: dict[str, dict[str, set[str]]] = {
    "fastapi": {
        "compose-base": {
            "PACKAGE_NAME",
            "PACKAGE_UNDERSCORE_NAME",
            "API_PORT",
            "SECRET_KEY",
            "ENVIRONMENT",
            "IMAGE_TAG",
            "PYTHON_VERSION",
            "POETRY_VERSION",
        },
        "compose-db": {
            "PACKAGE_NAME",
            "DB_BASE",
            "DB_USER",
            "DB_PASS",
            "DB_PORT",
            "IMAGE_TAG",
            "PYTHON_VERSION",
            "POETRY_VERSION",
            "POSTGRES_VERSION",
        },
        "compose-debug": {
            "PACKAGE_NAME",
            "PACKAGE_UNDERSCORE_NAME",
            "IMAGE_TAG",
            "DEBUG_PORT",
        },
        "compose-db-debug": {
            "PACKAGE_NAME",
            "DB_BASE",
            "DB_USER",
            "DB_PASS",
            "ADMINER_PORT",
        },
    }
}


def _get_required_vars_for_files(
    compose_type: str, compose_files: list[str]
) -> set[str]:
    """Determine required environment variables based on compose files being used.

    Args:
        compose_type: The compose type (e.g., `fastapi`)
        compose_files: List of compose file paths

    Returns:
        Set of environment variable names needed for the given files
    """
    type_requirements = _COMPOSE_VAR_REQUIREMENTS.get(compose_type, {})
    required_vars: set[str] = set()

    for file_path in compose_files:
        # Extract the base name without path and extension
        # Handle temp files like "compose-base.abc123.yml" -> "compose-base"
        file_name = Path(file_path).name
        # Remove .yml, .yaml extensions
        for ext in [".yml", ".yaml"]:
            if file_name.endswith(ext):
                file_name = file_name[: -len(ext)]
                break
        # Remove temp file hash if present (e.g., ".abc123")
        parts = file_name.split(".")
        base_name = (
            parts[0]
            if len(parts) > 1 and parts[-1].replace("_", "").replace("-", "").isalnum()
            else file_name
        )

        if base_name in type_requirements:
            required_vars.update(type_requirements[base_name])

    return required_vars


def _get_compose_env(
    image_tag: str | None = None,
    compose_type: str | None = None,
    compose_files: list[str] | None = None,
) -> dict[str, str]:
    """Get environment variables for `docker compose`.

    Only includes variables required by the compose files being used,
    plus all current OS environment variables for pass-through.

    Args:
        image_tag: Docker image tag to use
        compose_type: The compose type (e.g., `fastapi`) for variable filtering
        compose_files: List of compose file paths for variable filtering

    Returns:
        `dict` of environment variables for `docker compose`
    """
    import platform

    package_name = _get_package_name()

    all_vars = {
        "ADMINER_PORT": os.getenv("ADMINER_PORT", "8081"),
        "API_PORT": os.getenv("API_PORT", "8080"),
        "DB_BASE": os.getenv("DB_BASE", package_name),
        "DB_PASS": os.getenv("DB_PASS", ""),
        "DB_PORT": os.getenv("DB_PORT", "5432"),
        "DB_USER": os.getenv("DB_USER", package_name),
        "DEBUG_PORT": os.getenv("DEBUG_PORT", "5678"),
        "ENVIRONMENT": os.getenv("ENVIRONMENT", "production"),
        "IMAGE_TAG": image_tag or "latest",
        "PACKAGE_NAME": package_name,
        "PACKAGE_UNDERSCORE_NAME": package_name.replace("-", "_"),
        "POETRY_VERSION": _get_poetry_version(),
        "POSTGRES_VERSION": os.getenv("POSTGRES_VERSION", "17"),
        "PYTHON_VERSION": platform.python_version(),
        "SECRET_KEY": os.getenv("SECRET_KEY", ""),
    }

    if compose_type and compose_files:
        required_vars = _get_required_vars_for_files(compose_type, compose_files)
        filtered_vars = {k: v for k, v in all_vars.items() if k in required_vars}
    else:
        filtered_vars = all_vars

    return {**os.environ, "COMPOSE_MENU": "false", **filtered_vars}


def _get_compose_type() -> str:
    """Get the compose type from environment variable or default to 'fastapi'."""
    return os.getenv("COMPOSE_TYPE", "fastapi")


def _load_compose_files(
    debug: bool = False,
) -> tuple[list[str], list[Path], list[Path]]:
    """Load and resolve compose files.

    Returns:
        A 3-tuple of `(compose_files, temp_compose_files, temp_config_files)`.

        *temp_compose_files* are rendered YAML files consumed only by
        ``docker compose`` itself and may be removed once the command finishes
        parsing them.

        *temp_config_files* are files referenced by compose `configs:` blocks
        (e.g. `alembic.ini`) that are bind-mounted into running containers.
        They must persist for the lifetime of the stack and should only be
        cleaned up **after** ``docker compose` down`.
    """
    compose_files_env = os.getenv("COMPOSE_FILE")
    if compose_files_env:
        LOGGER.debug(
            "Using compose files from environment variable COMPOSE_FILE: %s",
            compose_files_env,
        )
        return compose_files_env.split(":"), [], []

    compose_type = os.environ["COMPOSE_TYPE"]
    compose_addons_str = os.getenv("COMPOSE_ADDONS", "")
    compose_addons = [a.strip() for a in compose_addons_str.split(":") if a.strip()]

    LOGGER.debug(
        "Loading compose files for type '%s' with addons: %s%s",
        compose_type,
        compose_addons if compose_addons else "none",
        " (debug mode)" if debug else "",
    )

    files_and_cleanups = [
        _resolve_compose_file(
            f"{compose_type.upper()}_COMPOSE_BASE",
            "compose-base.yml",
            "compose-base.yml.j2",
            render_template=True,
            type_identifier=compose_type,
        )
    ]

    # Resolve auxiliary configs needed by addons before rendering addon compose
    # files, so that absolute paths can be passed as template variables.
    temp_config_files: list[Path] = []
    addon_template_vars: dict[str, dict[str, str]] = {}

    if "db" in compose_addons and compose_type == "fastapi":
        alembic_path, alembic_cleanup = _ensure_alembic_config(compose_type)
        if alembic_path:
            addon_template_vars["db"] = {
                "alembic_config_path": str(alembic_path.resolve()),
            }
            if alembic_cleanup:
                temp_config_files.append(alembic_path)

    for addon in compose_addons:
        files_and_cleanups.append(
            _resolve_compose_file(
                f"{compose_type.upper()}_COMPOSE_{addon.upper()}",
                f"compose-{addon}.yml",
                f"compose-{addon}.yml.j2",
                render_template=True,
                type_identifier=compose_type,
                extra_template_vars=addon_template_vars.get(addon),
            )
        )

    if debug:
        files_and_cleanups.append(
            _resolve_compose_file(
                f"{compose_type.upper()}_COMPOSE_DEBUG",
                "compose-debug.yml",
                "compose-debug.yml.j2",
                render_template=True,
                type_identifier=compose_type,
            )
        )
        # Load debug overlays only for addons that were explicitly requested
        for addon in compose_addons:
            files_and_cleanups.append(
                _resolve_compose_file(
                    f"{compose_type.upper()}_COMPOSE_{addon.upper()}_DEBUG",
                    f"compose-{addon}-debug.yml",
                    f"compose-{addon}-debug.yml.j2",
                    render_template=True,
                    type_identifier=compose_type,
                )
            )

    overlay_files_str = os.getenv("COMPOSE_OVERLAY_FILES", "")
    if overlay_files_str:
        overlay_files = [f.strip() for f in overlay_files_str.split(":") if f.strip()]
        LOGGER.debug("Adding overlay compose files: %s", overlay_files)
        for overlay_file in overlay_files:
            files_and_cleanups.append((overlay_file, False))

    compose_files = [path for path, _ in files_and_cleanups]
    temp_compose_files = [Path(path) for path, cleanup in files_and_cleanups if cleanup]

    return compose_files, temp_compose_files, temp_config_files


def _load_and_prepare_compose(
    debug: bool = False,
    image_tag: str | None = None,
) -> tuple[list[str], list[Path], list[Path], dict[str, str]]:
    """Load compose files and prepare environment variables.

    Returns:
        A 4-tuple of (compose_files, temp_compose_files, temp_config_files, compose_env).
    """
    compose_files, temp_compose_files, temp_config_files = _load_compose_files(
        debug=debug
    )
    compose_type = _get_compose_type()
    compose_env = _get_compose_env(
        image_tag=image_tag, compose_type=compose_type, compose_files=compose_files
    )
    return compose_files, temp_compose_files, temp_config_files, compose_env


def _run_docker_compose_command(
    *args: str | None,
    compose_files: list[str],
    compose_env: dict[str, str],
) -> None:
    """Run `docker compose` with standard file and env-file arguments.

    Args:
        *args: Command arguments (None values are filtered out).
        compose_files: List of compose file paths.
        compose_env: Environment variables for the command.
    """
    _run_command(
        [
            *_compose_cmd_prefix(compose_files),
            *[arg for arg in args if arg is not None],
        ],
        env=compose_env,
    )


def _compose_cmd_prefix(compose_files: list[str]) -> list[str]:
    """Build the common `docker compose` command prefix with file and env-file flags."""
    return [
        "docker",
        "compose",
        "--project-directory",
        os.getcwd(),
        *[item for f in compose_files for item in ("-f", f)],
        *[item for env_file in tasks.envfile for item in ("--env-file", env_file)],
    ]


def _cleanup_temp_files(*file_lists: list[Path]) -> None:
    """Remove temporary files, ignoring files that are already gone."""
    for file_list in file_lists:
        for temp_file in file_list:
            try:
                temp_file.unlink()
            except FileNotFoundError:
                pass


@tasks.script(task_name="_stack-up", tags=["web", "containers", "fastapi"])
def _bring_up_fastapi_stack(
    debug: bool = False,
    no_cache: bool = False,
    detach: bool = False,
    services: str | None = None,
) -> None:
    # TODO: Don't mess with signals. Possibly use a shell-type task
    containerfile_text = _load_data_file("Containerfile")[1]

    commit_tag = _build_image(
        None,
        containerfile_text,
        Path("."),
        debug=debug,
        no_cache=no_cache,
        single_arch=True,
    )[1]

    _ensure_secrets_generated()

    compose_files, temp_compose_files, temp_config_files, compose_env = (
        _load_and_prepare_compose(
            debug=debug,
            image_tag=commit_tag,
        )
    )
    api_port = int(compose_env["API_PORT"])

    # When watch mode is active, `docker compose` needs the Containerfile present
    # in the project directory so that watch-triggered rebuilds can find it.
    watch_mode = debug and not detach
    local_containerfile = Path("Containerfile")
    wrote_containerfile = False
    if watch_mode and not local_containerfile.exists():
        local_containerfile.write_text(containerfile_text, encoding="utf-8")
        wrote_containerfile = True

    up_args = [
        "up",
        *(["--watch"] if debug and not detach else []),
        *(["--no-build"] if not (debug and not detach) else []),
        "--force-recreate",
        "--remove-orphans",
        *(["-d"] if detach else []),
        *(services.split(",") if services else []),
    ]

    try:
        LOGGER.info("Building and starting the application stack...")
        LOGGER.info(
            "Starting application. Once the stack is up, check the API docs at http://localhost:%i/api/docs",
            api_port,
        )
        if detach:
            _run_docker_compose_command(
                *up_args,
                compose_files=compose_files,
                compose_env=compose_env,
            )
            LOGGER.info("Application has started! To stop it, run poe stack-down")
        else:
            import signal

            process = subprocess.Popen(
                [
                    *_compose_cmd_prefix(compose_files),
                    *[arg for arg in up_args if arg is not None],
                ],
                env={**os.environ, **compose_env},
                text=True,
                preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN),
            )

            try:
                process.wait()
            except KeyboardInterrupt:
                LOGGER.debug("Received interrupt, forwarding to docker compose...")
                process.terminate()
                try:
                    # Wait for compose to exit; this can also be interrupted by a
                    # second Ctrl+C, which we simply ignore rather than bubbling
                    # out of the task. Without this guard the outer handler will
                    # see another KeyboardInterrupt and re-raise it, aborting the
                    # stack-down sequence.
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    LOGGER.warning("Compose did not exit in time; killing process")
                    process.kill()
                except KeyboardInterrupt:
                    LOGGER.debug("Second interrupt received while waiting; ignoring")
                # Once we've forwarded the signal and torn the stack down we can
                # return; there's no need for the KeyboardInterrupt to escape
                # past this function.
                return
    finally:
        if not detach:
            _cleanup_temp_files(temp_config_files)
        _cleanup_temp_files(temp_compose_files)
        if wrote_containerfile:
            try:
                local_containerfile.unlink()
            except FileNotFoundError:
                pass


_STACK_UP_DEBUG_HELP = "Enable debug mode (auto-loads all `*-debug.yml` compose files)."
_STACK_UP_NO_CACHE_HELP = "Do not use cache when building the image."
_STACK_UP_DETACH_HELP = "Run the stack in detached mode."
_STACK_UP_SERVICES_HELP = (
    "Optional comma-separated list of services to start (e.g. 'api,db'). "
    "If not provided, all services will be started."
)


tasks.add(
    task_name="stack-up",
    task_config={
        "help": f"""Bring up the development stack for the application.

    Args:
        debug: {_STACK_UP_DEBUG_HELP}
        no_cache: {_STACK_UP_NO_CACHE_HELP}
        detach: {_STACK_UP_DETACH_HELP}
        services: {_STACK_UP_SERVICES_HELP}
    """,
        "sequence": ["_stack-up", "stack-down"],
        "args": {
            "debug": {"help": _STACK_UP_DEBUG_HELP, "type": "boolean"},
            "no_cache": {"help": _STACK_UP_NO_CACHE_HELP, "type": "boolean"},
            "detach": {"help": _STACK_UP_DETACH_HELP, "type": "boolean"},
            "services": {"help": _STACK_UP_SERVICES_HELP},
        },
    },
    tags=["web", "containers", "fastapi"],
)


@tasks.script(task_name="stack-down", tags=["web", "containers", "fastapi"])
def fastapi_stack_down() -> None:
    """Bring down the development stack for the application."""
    compose_files, temp_compose_files, temp_config_files, compose_env = (
        _load_and_prepare_compose()
    )

    try:
        LOGGER.info("Bringing down the application stack...")
        _run_docker_compose_command(
            "rm",
            "-f",
            "-s",
            "-v",
            compose_files=compose_files,
            compose_env=compose_env,
        )
    finally:
        _cleanup_temp_files(temp_compose_files, temp_config_files)


@tasks.script(task_name="reset-db", tags=["web", "containers", "database", "fastapi"])
def fastapi_reset_db() -> None:
    """Reset the database by deleting the database volume."""
    compose_env = _load_and_prepare_compose()[3]

    volume_name = f"{_get_package_name()}-db-data"
    _run_command(
        ["docker", "volume", "rm", "-f", volume_name],
        capture_output=True,
        env=compose_env,
    )


@tasks.script(task_name="run-db-migrations", tags=["web", "containers", "database", "fastapi"])
def fastapi_run_db_migrations() -> None:
    """Run database migrations."""
    services = ["db", "migrator"]
    _bring_up_fastapi_stack(debug=False, detach=True, services=",".join(services))
    compose_files, _, _, compose_env = _load_and_prepare_compose()
    _run_docker_compose_command(
        "logs",
        "migrator",
        compose_files=compose_files,
        compose_env=compose_env,
    )
    fastapi_stack_down()


@tasks.script(task_name="db-shell", tags=["web", "containers", "database", "fastapi"])
def fastapi_db_shell() -> None:
    """Open a psql shell to the database container."""
    _bring_up_fastapi_stack(debug=False, no_cache=True, detach=True, services="db")
    try:
        compose_files, _, _, compose_env = _load_and_prepare_compose()

        _run_command(
            [
                "docker",
                "compose",
                *[item for f in compose_files for item in ("-f", f)],
                "exec",
                "-it",
                "db",
                "psql",
                "-U",
                os.getenv("DB_USER", _get_package_name()),
                os.getenv("DB_BASE", _get_package_name()),
            ],
            env=compose_env,
        )
    finally:
        fastapi_stack_down()


@tasks.script(tags=["containers", "debug"])
def container_shell(
    tag: str | None = None,
    shell: str = "/bin/bash",
    root: bool = False,
    no_echo_env: bool = False,
) -> None:
    """Run the debug image with an interactive shell.

    Behavior when `tag` is `None` mirrors `run_container`:
      - select the most-recently-built tag for the project's image (do not build).

    Args:
        tag: Image tag to use. If `None`, use the most-recently-built tag.
        shell: Shell to use inside the container.
        root: Whether to run the shell as root.
        no_echo_env: Whether to suppress printing environment variables on startup for debugging.
    """
    run_container(
        tag,
        entrypoint="/bin/sh",
        command=shell,
        root=root,
        echo_env=not no_echo_env,
    )
