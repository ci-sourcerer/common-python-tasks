import logging
import os
import re
import secrets
import shlex
from pathlib import Path

from . import utils

LOGGER = logging.getLogger(__name__)

TRUTHY_VALUES = {
    "1",
    "true",
    "yes",
    "on",
    "enabled",
    "enable",
    "y",
    "t",
}
WORKDIR_PATH_ENV_VAR = "WORKDIR_PATH"
WORKDIR_PATH_DEFAULT = "/workspace"
_AUTO_INJECTED_BUILD_ARG_ENV_VARS = (WORKDIR_PATH_ENV_VAR,)
_UV_INDEX_CREDENTIAL_PATTERN = re.compile(r"^UV_INDEX_(.+)_(USERNAME|PASSWORD)$")


def collect_uv_index_credentials() -> list[dict[str, str | None]]:
    """Collect present `UV_INDEX_{name}_{USERNAME,PASSWORD}` host env vars.

    Returns:
        A list of dicts with keys `index_name`, `username_env`, and
        `password_env`. Only indices with at least one credential set are
        included, sorted by index name.
    """
    found = {}
    for key in os.environ:
        match = _UV_INDEX_CREDENTIAL_PATTERN.match(key)
        if match:
            found.setdefault(match.group(1), set()).add(match.group(2))

    return [
        {
            "index_name": name,
            "username_env": f"UV_INDEX_{name}_USERNAME"
            if "USERNAME" in found[name]
            else None,
            "password_env": f"UV_INDEX_{name}_PASSWORD"
            if "PASSWORD" in found[name]
            else None,
        }
        for name in sorted(found)
    ]


def uv_index_secret_mounts(credentials: list[dict[str, str | None]]) -> list[str]:
    """Return Dockerfile ``--mount`` strings for UV index credentials.

    Args:
        credentials: Output of `collect_uv_index_credentials`.

    Returns:
        A list of ``type=secret,...`` strings for Dockerfile ``RUN --mount=``
        directives.
    """
    mounts = []
    for cred in credentials:
        name = cred["index_name"].lower()
        if cred["username_env"]:
            mounts.append(
                f"type=secret,id=uv_index_{name}_username,env={cred['username_env']}"
            )
        if cred["password_env"]:
            mounts.append(
                f"type=secret,id=uv_index_{name}_password,env={cred['password_env']}"
            )
    return mounts


def uv_index_secret_build_args(credentials: list[dict[str, str | None]]) -> list[str]:
    """Return ``docker build --secret`` arg pairs for UV index credentials.

    Args:
        credentials: Output of `collect_uv_index_credentials`.

    Returns:
        A flat list of ``--secret`` flag-value pairs for the docker build command.
    """
    args = []
    for cred in credentials:
        name = cred["index_name"].lower()
        if cred["username_env"]:
            args.extend(
                ["--secret", f"id=uv_index_{name}_username,env={cred['username_env']}"]
            )
        if cred["password_env"]:
            args.extend(
                ["--secret", f"id=uv_index_{name}_password,env={cred['password_env']}"]
            )
    return args


def env_truthy(env_var: str) -> bool:
    """Return `True` if the environment variable is set to a truthy value.

    Args:
        env_var: The name of the environment variable.

    Returns:
        `True` if the environment variable is set to a truthy value, `False` otherwise.
    """
    return os.getenv(env_var, "").lower() in TRUTHY_VALUES


def get_workdir_path() -> str:
    """Return the configured container workdir path.

    Returns:
        The workdir path from `WORKDIR_PATH`, or the project default.
    """
    return os.getenv(WORKDIR_PATH_ENV_VAR, WORKDIR_PATH_DEFAULT)


def get_python_variant() -> str:
    """Return the Python image variant for container builds.

    Returns:
        The variant from `CONTAINER_PYTHON_VARIANT`, or 'slim' by default.
        An empty string disables the variant (e.g., `FROM python:3.11`).
    """
    return os.getenv("CONTAINER_PYTHON_VARIANT", "slim").strip()


def inject_auto_build_args_from_env(
    build_args: dict[str, str] | None,
) -> dict[str, str]:
    """Inject configured environment variables into managed Docker build args.

    Environment-driven build args are only injected if they are set, and never
    override arguments already managed by the image builder.

    Args:
        build_args: Existing managed Docker build arguments.

    Returns:
        A build-arg dictionary with auto-injected env values merged in.
    """
    merged_build_args = dict(build_args or {})
    for env_var in _AUTO_INJECTED_BUILD_ARG_ENV_VARS:
        env_value = os.getenv(env_var)
        if env_value is not None:
            merged_build_args.setdefault(env_var, env_value)
    return merged_build_args


def parse_container_extensions() -> list[dict]:
    """Parse `CONTAINER_EXTENSION_FILES` and `CONTAINER_EXTENSIONS` (colon-delimited).

    Returns:
        A list of extension descriptor dictionaries with keys including `id`,
        `source`, `path`, and `bundle_name`.
    """
    exts: list[dict] = []
    files_raw = os.getenv("CONTAINER_EXTENSION_FILES")
    if files_raw:
        for part in split_colon_delimited_values(files_raw):
            pth = Path(part)
            exts.append(
                {
                    "id": (
                        pth.name.split("Dockerfile.", 1)[1]
                        if pth.name.startswith("Dockerfile.")
                        else pth.stem
                    ),
                    "source": "file",
                    "path": part,
                    "bundle_name": None,
                }
            )
    bundles_raw = os.getenv("CONTAINER_EXTENSIONS")
    if bundles_raw:
        for part in split_colon_delimited_values(bundles_raw):
            if not part:
                continue
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


def resolve_extension_content(descriptor: dict[str, str | None]) -> str:
    """Return the Dockerfile fragment for the given descriptor.

    Args:
        descriptor: Extension descriptor dictionary containing `source`,
            `path`, and `bundle_name` values.

    Returns:
        The Dockerfile fragment text to use for the extension.
    """

    if descriptor["source"] == "file":
        p = Path(descriptor["path"] or "")
        if not p.exists():
            utils.fatal(f"Extension Dockerfile not found: {p}")
        return p.read_text(encoding="utf-8")
    if descriptor["source"] == "bundle":
        bundle_name = descriptor["bundle_name"]
        out = utils.load_data_file(
            f"{bundle_name}/Dockerfile",
            type_identifier="dockerfile_extensions",
            fatal_on_missing=False,
        )
        if out is None:
            utils.fatal(f"Extension bundle not found: {bundle_name}")
        return out[1]
    utils.fatal(f"Unknown extension descriptor source: {descriptor['source']}")


def get_cache_id_suffix(no_cache: bool) -> str:
    """Return a cache-break suffix for Docker cache mount IDs.
    Args:
        no_cache: Whether to disable the Docker cache.

    Returns:
        If `no_cache` is enabled, a stable random suffix for the
        current task invocation; otherwise an empty string.
    """
    if not no_cache:
        return ""

    return f"-{secrets.token_hex(8)}"


def load_container_env_file(path: str | None = None) -> str | None:
    """Return the contents of a container env file if it exists and is non-empty.

    Args:
        path: Path to the container env file.

    Returns:
        The contents of the container env file if it exists and is non-empty, otherwise `None`.
    """

    if path is not None:
        container_env_path = Path(path)
        if not container_env_path.is_file():
            utils.fatal(f"Container env file not found: {path}")
    else:
        container_env_path = Path(".containerenv")
        if not container_env_path.is_file():
            return None

    container_env = container_env_path.read_text(encoding="utf-8").strip()
    return container_env if container_env else None


def split_delimited_values(
    value: str,
    separators: str = ":",
    allow_whitespace: bool = False,
) -> list[str]:
    """Split a delimited string while preserving quoted or escaped separators.

    Args:
        value: The string to split.
        separators: Explicit separator characters to use. Prefix a separator with
            a backslash to include it literally in a token.
        allow_whitespace: Treat whitespace as additional separators.

    Returns:
        A list of strings representing the parsed tokens.
    """
    if not value or not value.strip():
        return []

    lexer = shlex.shlex(value, posix=True)
    lexer.whitespace = separators + (" \t\r\n" if allow_whitespace else "")
    lexer.whitespace_split = True
    lexer.commenters = "#"
    return [token for token in lexer if token.strip()]


def split_colon_delimited_values(value: str) -> list[str]:
    """Split colon-delimited values while preserving quoted or escaped colons.

    Args:
        value: The string to split.

    Returns:
        The parsed tokens.
    """
    return split_delimited_values(value, separators=":", allow_whitespace=True)


def resolve_container_docker_build_args(
    cli_docker_build_args: tuple[str, ...], env_docker_build_args: str | None
) -> list[str]:
    """Resolve arguments passed directly to `docker build`.

    Args:
        cli_docker_build_args: Free arguments provided after the task's `--`
            separator.
        env_docker_build_args: Shell-tokenized arguments from the environment.

    Returns:
        The CLI arguments when provided, otherwise the environment arguments.
    """
    if cli_docker_build_args:
        return list(cli_docker_build_args)
    if not env_docker_build_args:
        return []

    try:
        return shlex.split(env_docker_build_args)
    except ValueError as error:
        utils.fatal(f"Invalid CONTAINER_DOCKER_BUILD_ARGS: {error}")


def resolve_container_dockerfile_hook_path(
    cli_hook_path: str | None, env_hook_path: str | None
) -> Path | None:
    """Resolve and validate the optional dockerfile hook script path.

    Args:
        cli_hook_path: Hook path provided via CLI argument.
        env_hook_path: Hook path provided by environment.

    Returns:
        The validated hook path, or `None` when unset.
    """
    raw_value = (
        cli_hook_path if cli_hook_path and cli_hook_path.strip() else env_hook_path
    )
    if raw_value is None or not raw_value.strip():
        return None

    hook_path = Path(raw_value.strip())
    if not hook_path.exists():
        utils.fatal(f"Dockerfile hook script not found: {hook_path}")
    if not hook_path.is_file():
        utils.fatal(f"Dockerfile hook path is not a file: {hook_path}")
    if not os.access(hook_path, os.X_OK):
        utils.fatal(f"Dockerfile hook script must be executable: {hook_path}")

    return hook_path


def parse_container_env_tokens(value: str | list[str] | None) -> list[str]:
    """Parse `KEY=VALUE` container env declarations from string or list input.

    Args:
        value: The string or list of container env declarations.

    Returns:
        A list of parsed container env tokens.
    """
    if value is None:
        return []

    if isinstance(value, list):
        tokens = [token.strip() for token in value if token and token.strip()]
    elif not value.strip():
        return []
    else:
        tokens = split_colon_delimited_values(value)

    for token in tokens:
        if "=" not in token or not token.split("=", 1)[0].strip():
            utils.fatal(
                f"Invalid container env token {token!r}; expected KEY=VALUE. "
                "Escape literal colons in values as \\: or quote the value."
            )

    return tokens


def _parse_container_envfile_paths(
    container_envfile: str | list[str] | None,
) -> list[str]:
    if container_envfile is None:
        return []
    if isinstance(container_envfile, list):
        return [path.strip() for path in container_envfile if path and path.strip()]
    if not container_envfile.strip():
        return []
    return split_colon_delimited_values(container_envfile)


def load_container_env_tokens(
    container_env: str | list[str] | None = None,
    container_envfile: str | list[str] | None = None,
) -> list[str]:
    """Load container env declarations from multiple sources in precedence order.

    Args:
        container_env: Inline container environment declarations.
        container_envfile: Paths to files containing environment declarations.

    Returns:
        Environment tokens ordered from lowest to highest precedence.
    """
    tokens: list[str] = []

    file_value = load_container_env_file()
    if file_value is not None:
        tokens.extend(parse_container_env_tokens(file_value))

    for path in _parse_container_envfile_paths(container_envfile):
        file_value = load_container_env_file(path)
        if file_value is not None:
            tokens.extend(parse_container_env_tokens(file_value))

    env_value = os.getenv("CONTAINER_ENV")
    if env_value and env_value.strip():
        tokens.extend(parse_container_env_tokens(env_value))

    tokens.extend(parse_container_env_tokens(container_env))

    return tokens


def parse_container_deps_source() -> tuple[Path | list[Path] | None, str | None]:
    """Return the source for dependency Dockerfile input.

    `CONTAINER_DEPS_CONTENT` is preferred and overrides `CONTAINER_DEPS_FILE`.
    `CONTAINER_DEPS_FILE` may contain a colon-delimited list of file paths.

    Returns:
        A tuple of `(dockerfile_path_or_paths, inline_content)`. One of the values
        may be `None` when not provided.
    """

    content = os.getenv("CONTAINER_DEPS_CONTENT")
    if content and content.strip():
        return None, content.strip()

    path_raw = os.getenv("CONTAINER_DEPS_FILE")
    if path_raw:
        paths = [Path(p.strip()) for p in split_colon_delimited_values(path_raw)]
        if not paths:
            return None, None
        for p in paths:
            if not p.exists():
                utils.fatal(f"CONTAINER_DEPS_FILE not found: {p}")
        return paths[0] if len(paths) == 1 else paths, None
    return None, None


def parse_container_deps() -> str | None:
    """Return the Dockerfile content for the deps image from environment.

    `CONTAINER_DEPS_CONTENT` overrides `CONTAINER_DEPS_FILE`.

    Returns:
        The resolved dependency Dockerfile content, or `None` when unset.
    """
    dockerfile_path, content = parse_container_deps_source()
    if content is not None:
        return content
    if dockerfile_path is not None:
        if isinstance(dockerfile_path, list):
            return "\n".join(
                p.read_text(encoding="utf-8").strip() for p in dockerfile_path
            ).strip()
        return dockerfile_path.read_text(encoding="utf-8").strip()
    return None


def parse_container_deps_mappings() -> dict[str, str] | None:
    """Parse `CONTAINER_DEPS_MAPPINGS` into dependency-name-to-path pairs.

    The env var should contain whitespace-separated mappings in the form
    `name:/target/path`.

    Returns:
        A dict of dependency names to destination paths, or `None` when unset.
    """

    raw = os.getenv("CONTAINER_DEPS_MAPPINGS")
    if not raw or not raw.strip():
        return None

    import shlex

    try:
        tokens = shlex.split(raw)
    except ValueError as exc:
        utils.fatal(f"Invalid CONTAINER_DEPS_MAPPINGS: {exc}")

    mappings: dict[str, str] = {}
    for token in tokens:
        if ":" not in token:
            utils.fatal(
                "CONTAINER_DEPS_MAPPINGS must contain pairs like "
                f"'name:/target/path'; invalid token: {token}",
            )
        name, dest = token.split(":", 1)
        name = name.strip()
        dest = dest.strip()
        if not name or not dest:
            utils.fatal(
                "CONTAINER_DEPS_MAPPINGS must provide both a dependency name and a destination path"
            )
        if name in mappings:
            utils.fatal(f"Duplicate dependency mapping for: {name}")
        mappings[name] = dest

    return mappings


def render_container_deps_move_script(mappings: dict[str, str]) -> str:
    """Render a Python script that moves deps from `/tmp/deps` into target paths.

    Args:
        mappings: Dependency names mapped to their destination paths.

    Returns:
        Executable Python script text, or an empty string for no mappings.
    """
    if not mappings:
        return ""

    import textwrap

    script_lines = [
        "import pathlib",
        "import shutil",
        "import sys",
        "",
        f"mappings = {repr(mappings)}",
        'source_root = pathlib.Path("/tmp/deps")',
        "",
        "for name, dest in mappings.items():",
        "    source_path = source_root / name",
        "    if not source_path.exists():",
        '        print(f"Dependency source not found: {source_path}", file=sys.stderr)',
        "        sys.exit(1)",
        "    dest_path = pathlib.Path(dest)",
        "    dest_path.parent.mkdir(parents=True, exist_ok=True)",
        "    shutil.move(str(source_path), str(dest_path))",
    ]

    return textwrap.dedent("\n".join(script_lines)).strip()


def get_container_deps_move_script() -> str | None:
    """Return the container dependency move script from env or path.

    Supports either inline executable script content via
    `CONTAINER_DEPS_MOVE_SCRIPT` or a host-side script file path via
    `CONTAINER_DEPS_MOVE_SCRIPT_PATH`.

    Returns:
        The configured move script text, or `None` when none is configured.
    """

    script_path_value = os.getenv("CONTAINER_DEPS_MOVE_SCRIPT_PATH")
    inline_script = os.getenv("CONTAINER_DEPS_MOVE_SCRIPT")

    if script_path_value and script_path_value.strip():
        if inline_script and inline_script.strip():
            LOGGER.warning(
                "Both CONTAINER_DEPS_MOVE_SCRIPT_PATH and CONTAINER_DEPS_MOVE_SCRIPT are set; using CONTAINER_DEPS_MOVE_SCRIPT_PATH."
            )
        script_path = Path(script_path_value)
        if not script_path.exists():
            utils.fatal(f"CONTAINER_DEPS_MOVE_SCRIPT_PATH not found: {script_path}")
        if not script_path.is_file():
            utils.fatal(f"CONTAINER_DEPS_MOVE_SCRIPT_PATH is not a file: {script_path}")
        content = script_path.read_text(encoding="utf-8")
        if not content.strip():
            utils.fatal(f"CONTAINER_DEPS_MOVE_SCRIPT_PATH is empty: {script_path}")
        return content.rstrip("\n")

    if inline_script is None:
        return None

    inline_script = inline_script.strip()
    return inline_script if inline_script else None


def get_prune_keep() -> int:
    """Return the integer value of CONTAINER_PRUNE_KEEP.

    Semantics:
        -1: keep all (no pruning)
        0: keep only the latest
        N: keep latest + N previous
    Defaults to -1 when unset or invalid.

    Returns:
        The parsed prune count as an integer.
    """
    raw = os.getenv("CONTAINER_PRUNE_KEEP")
    if raw is None:
        return -1
    try:
        return int(raw)
    except Exception:
        LOGGER.warning(
            "Invalid CONTAINER_PRUNE_KEEP value '%s' - defaulting to -1 (no prune)",
            raw,
        )
        return -1
