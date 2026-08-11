# This is a highly-specific module for handling Docker Compose for a cerrtain type of project layout
# This is not yet fully tested and may be heavily changed or even removed in the future

import logging
import os
import platform
import tempfile
from pathlib import Path
from shlex import quote
from typing import NoReturn, Sequence

from jinja2 import Template
from poethepoet_tasks import TaskCollection

from . import utils
from .env import get_workdir_path
from .project import get_package_manager, get_package_manager_version

LOGGER = logging.getLogger(__name__)


def ensure_alembic_config(compose_type: str) -> tuple[Path | None, bool]:
    """Render `alembic.ini` from the bundled template when a local copy is absent.

    Args:
        compose_type: The compose type to use when locating the bundled template.

    Returns:
        A tuple of `(path, should_cleanup)` where `path` is the rendered
        config path and `should_cleanup` indicates whether the file should be
        removed after use.
    """
    alembic_ini_path = Path("alembic.ini")
    if alembic_ini_path.exists():
        LOGGER.debug("Using existing alembic.ini")
        return alembic_ini_path, False

    generated_alembic_ini_path = Path(
        f".{compose_type}.alembic.ini.common-python-tasks"
    )
    if generated_alembic_ini_path.exists():
        LOGGER.debug("Using generated alembic.ini at %s", generated_alembic_ini_path)
        return generated_alembic_ini_path, True

    result = utils.load_data_file(
        "alembic.ini.j2", type_identifier=compose_type, fatal_on_missing=False
    )
    if result is None:
        return None, False

    _, template_content = result
    rendered = Template(template_content).render(
        package_name=utils.get_package_name(use_underscores=True),
    )
    generated_alembic_ini_path.write_text(rendered, encoding="utf-8")
    LOGGER.debug("Rendered bundled alembic.ini.j2 to %s", generated_alembic_ini_path)
    return generated_alembic_ini_path, True


def render_file(
    env_var_name: str,
    local_filename: str,
    data_filename: str,
    render_template: bool = False,
    type_identifier: str = "generic",
    extra_template_vars: dict[str, str] | None = None,
    suffix: str = ".rendered",
) -> tuple[Path, bool]:
    """Render a file template with env/local/data precedence.

    Args:
        env_var_name: Environment variable name for overriding the config path.
        local_filename: Local filename to check before falling back to bundled data.
        data_filename: Bundled data file to use when no local config exists.
        render_template: Whether to render the file as a Jinja2 template.
        type_identifier: Data directory identifier for bundled resources.
        extra_template_vars: Additional template variables to pass when rendering.
        suffix: Suffix to use for temporary rendered files.

    Returns:
        A tuple of `(Path, bool)` where the first item is the resolved file path
        and the second item indicates whether the file should be removed later.
    """
    resolved_path = utils.get_config_path(
        env_var_name,
        local_filename,
        data_filename,
        type_identifier=type_identifier,
    )
    if resolved_path is None:
        utils.fatal(f"No configuration rendered for {data_filename}")

    path_obj = Path(resolved_path)
    should_template = render_template or path_obj.suffix == ".j2"

    if should_template:
        package_name = utils.get_package_name()
        env_prefix = os.getenv(
            "ENV_PREFIX",
            (
                utils.package_name_to_underscore(package_name.upper())
                if package_name
                else ""
            ),
        )
        template_vars = {
            "PACKAGE_NAME": package_name,
            "PACKAGE_UNDERSCORE_NAME": (
                utils.package_name_to_underscore(package_name) if package_name else ""
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
            suffix=suffix,
        )
        temp_path = Path(tf.name)
        tf.write(rendered)
        tf.close()
        return temp_path, True

    return path_obj, False


def read_dotenv(path: Path, error_on_fail: bool = False) -> dict[str, str]:
    """Parse a simple `.env` file into a `dict` (`KEY=VALUE`; ignore comments).

    Args:
        path: Path to the `.env` file.
        error_on_fail: Whether to raise a fatal error if parsing fails.

    Returns:
        A dictionary of environment variables parsed from the file.
    """

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
        if error_on_fail:
            utils.fatal(f"Failed to parse .env file {path}: {exc}")
        else:
            LOGGER.debug("Failed to parse .env file %s: %s", path, exc)
    return env


def append_dotenv(path: Path, items: dict[str, str]) -> None:
    """Append key/value pairs to `.env` with a generated header comment.

    Args:
        path: Path to the `.env` file.
        items: Environment variables to append to the file.
    """
    from datetime import datetime

    header = f"\n# Auto-generated by common_python_tasks on {datetime.now().isoformat(timespec='seconds')}\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(header)
        for k, v in items.items():
            f.write(f"{k}={v}\n")


def get_or_generate_secret(
    key_name: str, length_bytes: int = 32, set_in_env: bool = True
) -> str:
    """Get an env var or generate, store in `.env`, and return it.

    Args:
        key_name: The environment variable key to read or generate.
        length_bytes: Number of random bytes to use when generating a secret.
        set_in_env: Whether to populate the secret into `os.environ`.

    Returns:
        The existing or generated secret value.

    Notes:
        - Respects already-set environment variables.
        - If not set, checks `.env` for an existing value.
        - Otherwise generates with `secrets.token_hex(length_bytes)`, appends to `.env`,
          logs at `INFO`, and returns the value.
    """
    import secrets

    existing = os.getenv(key_name)
    if existing:
        return existing

    dotenv_path = Path(".env")
    existing_in_file = read_dotenv(dotenv_path).get(key_name)
    if existing_in_file:
        if set_in_env:
            os.environ[key_name] = existing_in_file
        return existing_in_file

    token = secrets.token_hex(length_bytes)
    try:
        append_dotenv(dotenv_path, {key_name: token})
        LOGGER.info("Generated %s and stored it in .env", key_name)
    except Exception as exc:
        LOGGER.warning(
            "Failed to persist %s to .env (%s); using in-memory only", key_name, exc
        )
    if set_in_env:
        os.environ[key_name] = token
    return token


def ensure_secrets_generated() -> None:
    """Ensure required secrets exist and persist them to `.env`."""
    get_or_generate_secret("SECRET_KEY")
    get_or_generate_secret("DB_PASS")


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
            "PACKAGE_MANAGER",
            "PACKAGE_MANAGER_VERSION",
        },
        "compose-db": {
            "PACKAGE_NAME",
            "DB_BASE",
            "DB_USER",
            "DB_PASS",
            "DB_PORT",
            "IMAGE_TAG",
            "PYTHON_VERSION",
            "PACKAGE_MANAGER",
            "PACKAGE_MANAGER_VERSION",
            "POSTGRES_VERSION",
            "WORKDIR_PATH",
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


def get_required_vars_for_files(
    compose_type: str, compose_files: list[Path]
) -> set[str]:
    """Determine required environment variables based on compose files being used.

    Args:
        compose_type: The compose type (e.g., `fastapi`).
        compose_files: List of compose file paths.

    Returns:
        Set of environment variable names needed for the given files.
    """
    type_requirements = _COMPOSE_VAR_REQUIREMENTS.get(compose_type, {})
    required_vars: set[str] = set()

    for file_path in compose_files:
        file_name = file_path.name
        for ext in (".yml", ".yaml"):
            if file_name.endswith(ext):
                file_name = file_name.removesuffix(ext)
                break
        parts = file_name.split(".")
        base_name = (
            parts[0]
            if len(parts) > 1 and parts[-1].replace("_", "").replace("-", "").isalnum()
            else file_name
        )

        if base_name in type_requirements:
            required_vars.update(type_requirements[base_name])

    return required_vars


def get_compose_env(
    image_tag: str | None = None,
    compose_type: str | None = None,
    compose_files: list[Path] | None = None,
) -> dict[str, str]:
    """Get environment variables for `docker compose`.

    Only includes variables required by the compose files being used,
    plus all current OS environment variables for pass-through.

    Args:
        image_tag: Docker image tag to use.
        compose_type: The compose type (e.g., `fastapi`) for variable filtering.
        compose_files: List of compose file paths for variable filtering.

    Returns:
        `dict` of environment variables for `docker compose`.
    """
    package_name = utils.get_package_name()

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
        "PACKAGE_MANAGER": get_package_manager(),
        "PACKAGE_MANAGER_VERSION": get_package_manager_version(),
        "PACKAGE_UNDERSCORE_NAME": utils.package_name_to_underscore(package_name),
        "WORKDIR_PATH": get_workdir_path(),
        "POSTGRES_VERSION": os.getenv("POSTGRES_VERSION", "17"),
        "PYTHON_VERSION": platform.python_version(),
        "SECRET_KEY": os.getenv("SECRET_KEY", ""),
    }

    if compose_type and compose_files:
        required_vars = get_required_vars_for_files(compose_type, compose_files)
        filtered_vars = {k: v for k, v in all_vars.items() if k in required_vars}
    else:
        filtered_vars = all_vars

    return {**os.environ, "COMPOSE_MENU": "false", **filtered_vars}


def get_compose_type() -> str:
    """Get the compose type from environment variable.

    Returns:
        The compose type string from `COMPOSE_TYPE`, defaulting to `fastapi`.
    """
    return os.getenv("COMPOSE_TYPE", "fastapi")


def load_compose_files(
    debug: bool = False,
) -> tuple[list[Path], list[Path], list[Path]]:
    """Load and resolve compose files.

    Args:
        debug: Whether to include debug compose files in the result.

    Returns:
        A 3-tuple of `(compose_files, temp_compose_files, temp_config_files)`.

        *temp_compose_files* are rendered YAML files consumed only by
        `docker compose` itself and may be removed once the command finishes
        parsing them.

        *temp_config_files* are files referenced by compose `configs:` blocks
        (e.g. `alembic.ini`) that are bind-mounted into running containers.
        They must persist for the lifetime of the stack and should only be
        cleaned up **after** `docker compose` down`.
    """

    from .env import split_colon_delimited_values

    compose_files_env = os.getenv("COMPOSE_FILE")
    if compose_files_env:
        LOGGER.debug(
            "Using compose files from environment variable COMPOSE_FILE: %s",
            compose_files_env,
        )
        return (
            [Path(path) for path in split_colon_delimited_values(compose_files_env)],
            [],
            [],
        )

    compose_type = get_compose_type()
    compose_addons_str = os.getenv("COMPOSE_ADDONS", "")
    compose_addons = split_colon_delimited_values(compose_addons_str)

    LOGGER.debug(
        "Loading compose files for type '%s' with addons: %s%s",
        compose_type,
        compose_addons if compose_addons else "none",
        " (debug mode)" if debug else "",
    )

    files_and_cleanups = [
        render_file(
            f"{compose_type.upper()}_COMPOSE_BASE",
            "compose-base.yml",
            "compose-base.yml.j2",
            render_template=True,
            type_identifier=compose_type,
            suffix=".yml",
        )
    ]

    temp_config_files = []
    addon_template_vars = {}

    if "db" in compose_addons and compose_type == "fastapi":
        alembic_path, alembic_cleanup = ensure_alembic_config(compose_type)
        if alembic_path:
            addon_template_vars["db"] = {
                "alembic_config_path": str(alembic_path.resolve()),
            }
            if alembic_cleanup:
                temp_config_files.append(alembic_path)

    for addon in compose_addons:
        files_and_cleanups.append(
            render_file(
                f"{compose_type.upper()}_COMPOSE_{addon.upper()}",
                f"compose-{addon}.yml",
                f"compose-{addon}.yml.j2",
                render_template=True,
                type_identifier=compose_type,
                extra_template_vars=addon_template_vars.get(addon),
                suffix=".yml",
            )
        )

    if debug:
        files_and_cleanups.append(
            render_file(
                f"{compose_type.upper()}_COMPOSE_DEBUG",
                "compose-debug.yml",
                "compose-debug.yml.j2",
                render_template=True,
                type_identifier=compose_type,
                suffix=".yml",
            )
        )
        for addon in compose_addons:
            files_and_cleanups.append(
                render_file(
                    f"{compose_type.upper()}_COMPOSE_{addon.upper()}_DEBUG",
                    f"compose-{addon}-debug.yml",
                    f"compose-{addon}-debug.yml.j2",
                    render_template=True,
                    type_identifier=compose_type,
                    suffix=".yml",
                )
            )

    overlay_files_str = os.getenv("COMPOSE_OVERLAY_FILES", "")
    if overlay_files_str:
        overlay_files = split_colon_delimited_values(overlay_files_str)
        LOGGER.debug("Adding overlay compose files: %s", overlay_files)
        for overlay_file in overlay_files:
            files_and_cleanups.append((Path(overlay_file), False))

    compose_files = [path for path, _ in files_and_cleanups]
    temp_compose_files = [Path(path) for path, cleanup in files_and_cleanups if cleanup]

    return compose_files, temp_compose_files, temp_config_files


def load_and_prepare_compose(
    debug: bool = False,
    image_tag: str | None = None,
) -> tuple[list[Path], list[Path], list[Path], dict[str, str]]:
    """Load compose files and prepare environment variables.

    Args:
        debug: Whether to include debug compose files.
        image_tag: Optional Docker image tag to include in compose environment.

    Returns:
        A 4-tuple of `(compose_files, temp_compose_files, temp_config_files, compose_env)`.
    """
    compose_files, temp_compose_files, temp_config_files = load_compose_files(
        debug=debug
    )
    compose_type = get_compose_type()
    compose_env = get_compose_env(
        image_tag=image_tag, compose_type=compose_type, compose_files=compose_files
    )
    return compose_files, temp_compose_files, temp_config_files, compose_env


def run_docker_compose_command(
    *args: str | None,
    compose_files: list[Path],
    compose_env: dict[str, str],
    tasks: TaskCollection,
) -> None:
    """Run `docker compose` with standard file and env-file arguments.

    Python has issues running interactive `docker compose` commands directly (e.g.
    `up`) because of how it handles subprocess I/O and signals, so instead, for
    those, consider using `_build_exec_script`.

    Args:
        *args: Command arguments (None values are filtered out).
        compose_files: List of compose file paths.
        compose_env: Environment variables for the command.
        tasks: Poe task collection that supplies configured env files.
    """

    utils.run_command(
        [
            *compose_cmd_prefix(compose_files, tasks),
            *[arg for arg in args if arg is not None],
        ],
        env=compose_env,
    )


def compose_cmd_prefix(
    compose_files: list[Path], tasks: TaskCollection
) -> Sequence[str]:
    """Build the common `docker compose` command prefix with file and env-file flags.

    Args:
        compose_files: List of compose file paths to include.
        tasks: Poe TaskCollection containing envfile paths.

    Returns:
        The full docker compose command prefix as a sequence of arguments.
    """
    return [
        "docker",
        "compose",
        "--project-directory",
        str(Path.cwd()),
        *[item for f in compose_files for item in ("-f", str(f))],
        *[item for env_file in tasks.envfile for item in ("--env-file", str(env_file))],
    ]


def cleanup_temp_files(*file_lists: list[Path]) -> None:
    """Remove temporary files, ignoring files that are already gone.

    Args:
        *file_lists: One or more lists of temporary file paths to remove.
    """
    for file_list in file_lists:
        for temp_file in file_list:
            try:
                temp_file.unlink()
            except FileNotFoundError:
                pass


def build_exec_script(
    command: Sequence[str | Path],
    cleanup_paths: list[Path] | None = None,
    teardown_command: Sequence[str | Path] | None = None,
) -> Path:
    """Build a self-deleting shell script that runs a command with cleanup.

    The generated script:

    - Self-deletes via a `trap` on `EXIT`
    - Removes `cleanup_paths` after the command exits
    - Optionally runs a `teardown_command` (e.g. `docker compose rm`)
      after the main command finishes (you could also use this to re-enter a task)

    Args:
        command: The command to run as the main process.
        cleanup_paths: Temporary files to delete after the command exits.
        teardown_command: An optional shell command (as an arg list) to run
            after the main command exits, e.g.
            `['docker', 'compose', ..., 'rm', '-f', '-s', '-v']`.

    Returns:
        Absolute path to the temporary script file.
    """
    script_fd = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        delete=False,
        prefix="compose-exec.",
        suffix=".sh",
    )
    script_path = Path(script_fd.name)
    script_path_str = str(script_path.resolve())

    lines = [
        "#!/bin/sh",
        f"SCRIPT_PATH={quote(script_path_str)}",
        "trap 'rm -f \"$SCRIPT_PATH\"' EXIT",
        "",
        " ".join(quote(str(arg)) for arg in command),
    ]

    if teardown_command:
        lines.append("")
        lines.append("# Teardown: remove containers/volumes")
        lines.append(" ".join(quote(str(arg)) for arg in teardown_command))

    if cleanup_paths:
        lines.append("")
        lines.append("# Clean up temporary files")
        for path in cleanup_paths:
            lines.append(f"rm -f {quote(str(path))}")

    lines.append("")

    script_path.write_text("\n".join(lines), encoding="utf-8")
    script_path.chmod(0o700)

    return script_path


def exec_script(script_path: Path | str, env: dict[str, str] | None = None) -> NoReturn:
    """Replace the current process with the given shell script.

    Args:
        script_path: Path to the shell script to execute.
        env: Optional environment variables to use for the executed script.

    Returns:
        This function never returns; it replaces the current process.
    """

    LOGGER.debug("Exec handoff to script: %s", script_path)
    os.execvpe("/bin/sh", ["/bin/sh", str(script_path)], env or os.environ)
