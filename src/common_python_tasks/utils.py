import json
import logging
import mimetypes
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, NoReturn, Sequence

from poethepoet_tasks import TaskCollection

LOGGER = logging.getLogger(__name__)


def env_truthy(env_var: str) -> bool:
    """Return `True` if the environment variable is set to a truthy value.

    Args:
        env_var: The name of the environment variable.

    Returns:
        True if the environment variable is set to a truthy value, False otherwise.
    """
    return os.getenv(env_var, "").lower() in {
        "1",
        "true",
        "yes",
        "on",
        "enabled",
        "y",
        "t",
    }


def package_name_to_underscore(package_name: str) -> str:
    """Convert a package name to an underscore-separated name for importlib.

    Args:
        package_name: The original package name, which may contain hyphens.

    Returns:
        The package name with hyphens replaced by underscores.
    """
    return package_name.replace("-", "_")


@lru_cache
def is_package_installed(package_name: str) -> bool:
    """Check if a package is installed and can be imported.

    Args:
        package_name: The name of the package to check.

    Returns:
        True if the package is installed, False otherwise.
    """
    from importlib.util import find_spec

    is_installed = find_spec(package_name_to_underscore(package_name)) is not None
    if not is_installed:
        LOGGER.debug("%s is not installed", package_name)

    return is_installed


def fatal(message: str, exit_code: int = 1) -> None:
    """Log a critical error message and exit the program.

    Args:
        message: The error message to log.
        exit_code: The exit code to use when terminating the program.
    """
    import sys

    LOGGER.critical(message)
    sys.exit(exit_code)


def require_package(package_name: str) -> None:
    """Ensure that a package is installed.

    Args:
        package_name: The name of the package to check.

    Raises:
        SystemExit: If the package is not installed.
    """
    if not is_package_installed(package_name):
        fatal(f"{package_name} is not installed")


def run_available_tools(
    tools: list[tuple[Callable[..., None], str]], none_available_message: str
) -> None:
    """Run a list of tools if they are available.

    Args:
        tools: A list of tuples containing a callable and the name of the required
            package.
        none_available_message: The message to log if none of the tools are available.
    """
    ran_any = False
    for fn, package in tools:
        if is_package_installed(package):
            fn()
            ran_any = True
    if not ran_any:
        fatal(none_available_message)


def get_authors() -> list[tuple[str, str]]:
    """Return a list of authors from the pyproject.toml file.

    Returns:
        A list of tuples containing the name and email of each author.
    """
    import tomllib

    return [
        ((a.get("name") or "").strip(), (a.get("email") or "").strip().strip("<>"))
        for a in tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
        .get("project", {})
        .get("authors", [])
    ]


def get_local_poetry_plugin_version(package_name: str) -> str | None:
    """Return a version from the local Poetry plugin installation if present.

    Args:
        package_name: The name of the package to check.

    Returns:
        The version of the local Poetry plugin if present, None otherwise.
    """
    plugins_dir = Path(".poetry/plugins")
    if not plugins_dir.is_dir():
        return None

    candidates = {
        package_name,
        package_name_to_underscore(package_name),
        package_name.replace("_", "-"),
    }

    for metadata_path in plugins_dir.glob("*.dist-info/METADATA"):
        try:
            metadata_text = metadata_path.read_text(encoding="utf-8")
        except OSError:
            continue

        name = None
        version = None
        for line in metadata_text.splitlines():
            if line.startswith("Name:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("Version:"):
                version = line.split(":", 1)[1].strip()
            if name is not None and version is not None:
                break

        if name and version and name in candidates:
            return version
    return None


def run_command(
    command: Sequence[str | Path | None],
    capture_output: bool = False,
    acceptable_returncodes: Sequence[int] | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Run a command as a subprocess and handle errors.

    Args:
        command: The command to run, as a sequence of strings or Paths. None values
            will be filtered out.
        capture_output: Whether to capture stdout and stderr.
        acceptable_returncodes: A set of acceptable return codes. If the command exits
            with a code not in this set, it will be treated as an error.
        env: An optional dictionary of environment variables to set for the command.
            This will be merged with the current environment.

    Returns:
        The `CompletedProcess` instance from the subprocess run.
    """
    import subprocess
    from shlex import quote

    if acceptable_returncodes is None:
        acceptable_returncodes = {0}

    command = [str(c) for c in command if c is not None]

    bold_command_display = (
        f"\033[1m{' '.join([quote(str(arg)) for arg in command])}\033[0m"
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


def load_data_file(
    file_name: str, type_identifier: str = "generic", fatal_on_missing: bool = True
) -> tuple[Path, str] | None:
    """Load a data file from the package resources.

    Args:
        file_name: The name of the data file to load.
        type_identifier: The type of data file.
        fatal_on_missing: Whether to raise an error if the file is not found.

    Returns:
        A tuple containing the `Path` to the data file and its contents as a string, or
            `None` if the file is not found and fatal_on_missing is `False`.
    """
    from importlib.resources import files

    try:
        data_files = files("common_python_tasks") / "data" / type_identifier
        data_file = data_files / file_name
        return (Path(str(data_file)), data_file.read_text())
    except FileNotFoundError as e:
        if fatal_on_missing:
            fatal(f"Data file not found: {file_name} ({e})")
        return None


def get_dirty_files(ignore: list[Path] | None = None) -> list[Path]:
    """Get a list of dirty files in the git repository, excluding any specified in the
    ignore list.

    Args:
        ignore: A list of file paths to ignore.

    Returns:
        A list of `Path` objects representing the dirty files.
    """
    if ignore is None:
        ignore = []

    ignore_set = {Path(p) for p in ignore}

    return [
        file_path
        for file_path in [
            Path(line[3:])
            for line in run_command(
                ["git", "status", "--porcelain"], capture_output=True
            ).stdout.splitlines()
            if line
        ]
        if file_path not in ignore_set
    ]


def get_version(ignore: list[Path] | None = None) -> str:
    """Get the current version of the project using git tags, marking it as dirty if
    there are uncommitted changes that are not in the ignore list.

    Args:
        ignore: A list of file paths to ignore when determining if the repository is dirty.

    Returns:
        The current version of the project as a string.
    """
    from dunamai import Style, Version

    if ignore is None:
        ignore = []

    dirty_files = get_dirty_files(ignore=ignore)
    LOGGER.debug("Dirty files: %s", dirty_files)

    return Version.from_git().serialize(
        style=Style.Pep440,
        dirty=bool(dirty_files),
    )


def get_image_tag(ignore: list[Path] | None = None) -> str:
    """Get a version string suitable for use as a Docker image tag, based on the
    current git version and whether there are uncommitted changes that are not in the
    ignore list.

    Args:
        ignore: A list of file paths to ignore when determining if the repository is
            dirty.

    Returns:
        A version string suitable for use as a Docker image tag.
    """
    if ignore is None:
        ignore = []

    return (
        get_version(ignore=ignore)
        .replace(".post", "-post")
        .replace(".dev", "-dev")
        .replace("+", "-")
    )


def has_tags_later_in_history() -> bool:
    """Check if there are any git tags that are ancestors of the current HEAD, which
    would indicate that the current commit is not at the tip of a tagged version.

    Returns:
        `True` if there are tags later in the history, `False` otherwise.
    """
    result = run_command(
        ["git", "tag"],
        capture_output=True,
        acceptable_returncodes={0, 128},
    )
    if result.returncode != 0 or not result.stdout.strip():
        return False

    for tag in result.stdout.strip().split("\n"):
        check_result = run_command(
            ["git", "merge-base", "--is-ancestor", "HEAD", tag],
            capture_output=True,
            acceptable_returncodes={0, 1},
        )
        if check_result.returncode == 1:
            return True

    return False


def get_dockerhub_username() -> str:
    """Get the Docker Hub username from the environment variable or fallback to the
    current system user.

    Returns:
        The Docker Hub username as a string.
    """
    from getpass import getuser

    return os.getenv("DOCKERHUB_USERNAME") or getuser()


def get_container_registry_url() -> str:
    """Get the container registry URL from the environment variable or fallback to
    Docker Hub with the username.

    Returns:
        The container registry URL as a string.
    """
    return os.environ.get(
        "CONTAINER_REGISTRY_URL",
        f"docker.io/{get_dockerhub_username()}",
    ).strip()


def get_package_name(use_underscores: bool = False) -> str:
    """Return the package name from environment or pyproject configuration.

    Args:
        use_underscores: Whether to normalize hyphenated names to underscores.

    Returns:
        The package name, with hyphens replaced by underscores if requested.
    """
    import tomllib

    name = os.getenv("PACKAGE_NAME") or tomllib.loads(
        Path("pyproject.toml").read_text()
    ).get("project", {}).get("name")
    if use_underscores and name:
        name = package_name_to_underscore(name)
    return name


def get_full_image_name() -> str:
    """Return the full container image name for the current package.

    Returns:
        The fully qualified image name including registry and package name.
    """
    return f"{get_container_registry_url()}/{get_package_name()}"


@lru_cache
def get_poetry_version() -> str:
    """Return the installed Poetry version string.

    Returns:
        The Poetry version parsed from the output of `poetry --version`.
    """
    return (
        run_command(["poetry", "--version"], capture_output=True)
        .stdout.strip()
        .split()[-1]
    )[0:-1]


@lru_cache
def get_installed_requirement_version(requirement_name: str) -> str | None:
    """Return the installed version for a Python requirement name.

    This helper is intended for dependencies that should already be available in
    the active Python environment, such as development tools installed in the
    current virtualenv.

    It normalizes extras like `package[extra]` and tries common name variants
    with hyphens and underscores. If the package is not available to
    importlib.metadata, it falls back to `poetry show` and then
    `poetry self show`.

    Args:
        requirement_name: The requirement name to lookup.

    Returns:
        The installed version string, or `None` if the package cannot be resolved.
    """
    from importlib import metadata

    package_name = requirement_name.split("[", 1)[0]
    candidates = {
        package_name,
        package_name_to_underscore(package_name),
        package_name.replace("_", "-"),
    }

    for candidate in candidates:
        try:
            return metadata.version(candidate)
        except metadata.PackageNotFoundError:
            pass

    def _query_poetry_runtime_version(candidate: str) -> str | None:
        result = run_command(
            [
                "poetry",
                "run",
                "python",
                "-c",
                f"from importlib import metadata; print(metadata.version({candidate!r}))",
            ],
            capture_output=True,
            acceptable_returncodes={0, 1},
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            if version:
                return version
        return None

    version = get_local_poetry_plugin_version(package_name)
    if version:
        return version

    for candidate in candidates:
        version = _query_poetry_runtime_version(candidate)
        if version:
            return version

    def _parse_poetry_show_version(output: str) -> str | None:
        for line in output.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            if key.strip() == "version":
                return value.strip()
        return None

    for cmd in (
        ["poetry", "show", package_name],
        ["poetry", "self", "show", package_name],
    ):
        result = run_command(cmd, capture_output=True, acceptable_returncodes={0, 1})
        if result.returncode == 0:
            version = _parse_poetry_show_version(result.stdout)
            if version:
                return version
    return None


@lru_cache
def read_pyproject_toml() -> dict[str, Any]:
    """Read and parse the `pyproject.toml` file.

    Returns:
        A dictionary representing the contents of the `pyproject.toml` file.
    """
    import tomllib

    return tomllib.loads(Path("pyproject.toml").read_text())


def extract_poe_script_tags(include_script: str, argument_name: str) -> set[str] | None:
    """Extract a tag list argument from a Poe include_script expression.

    Args:
        include_script: The raw Poe include_script value.
        argument_name: The argument name to extract, such as `include_tags` or
            `exclude_tags`.

    Returns:
        A set of parsed tag strings, or `None` if parsing fails.
    """
    import ast
    import re

    match = re.search(rf"{argument_name}\s*=\s*(\[[^\]]*\])", include_script)
    if match is None:
        return None

    try:
        parsed = ast.literal_eval(match.group(1))
    except (ValueError, SyntaxError):
        LOGGER.warning(
            "Failed to parse %s from tool.poe.include_script: %s",
            argument_name,
            include_script,
        )
        return None

    if not isinstance(parsed, (list, tuple, set)):
        return None

    return {str(tag).strip() for tag in parsed if str(tag).strip()}


@lru_cache
def is_task_tag_included(tag: str) -> bool:
    """Return whether a task tag is included by current Poe include_script rules.

    Args:
        tag: The task tag to evaluate.

    Returns:
        True if the tag is included, False if it is excluded by Poe include_script.
    """
    include_script = (
        read_pyproject_toml().get("tool", {}).get("poe", {}).get("include_script")
    )
    if not isinstance(include_script, str):
        return True

    include_tags = extract_poe_script_tags(include_script, "include_tags")
    if include_tags is not None:
        return tag in include_tags

    exclude_tags = extract_poe_script_tags(include_script, "exclude_tags")
    if exclude_tags is not None:
        return tag not in exclude_tags

    return True


def get_config_path(
    env_var_name: str,
    local_config_filename: str,
    data_config_filename: str,
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
        pyproject_data = read_pyproject_toml()
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

    bundled_config = load_data_file(
        data_config_filename, type_identifier=type_identifier
    )
    config_path = Path(bundled_config[0])
    LOGGER.debug("Using bundled config file: %s", config_path)
    return config_path


def parse_container_extensions() -> list[dict]:
    """Parse `CONTAINER_EXTENSION_FILES` and `CONTAINER_EXTENSIONS` (colon-delimited).

    Returns:
        A list of extension descriptor dictionaries with keys including `id`,
        `source`, `path`, and `bundle_name`.
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
            fatal(f"Extension Dockerfile not found: {p}")
        return p.read_text(encoding="utf-8")
    if descriptor["source"] == "bundle":
        bundle_name = descriptor["bundle_name"]
        out = load_data_file(
            f"{bundle_name}/Dockerfile",
            type_identifier="dockerfile_extensions",
            fatal_on_missing=False,
        )
        if out is None:
            fatal(f"Extension bundle not found: {bundle_name}")
        return out[1]
    fatal(f"Unknown extension descriptor source: {descriptor['source']}")


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
            "Invalid CONTAINER_PRUNE_KEEP value '%s' - defaulting to -1 (no prune)", raw
        )
        return -1


def prune_images_keep(
    full_name: str,
    package_name: str,
    keep: int,
    protect_tags: Sequence[str] | None = None,
) -> None:
    """Prune images for `full_name` keeping the most-recent `keep + 1` images.

    Args:
        full_name: The full image name prefix to prune.
        package_name: The package image name used to identify matching images.
        keep: The number of older images to retain, where -1 means keep all.
        protect_tags: Optional tags to preserve regardless of pruning.

    Notes:
        - `keep` follows CONTAINER_PRUNE_KEEP semantics: -1 => do nothing.
        - `protect_tags` are never removed even if older.
    """
    if keep < 0:
        return
    if protect_tags is None:
        protect_tags = []

    retain_count = keep + 1

    res = run_command(
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
    tags_in_order = []
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
                run_command(["docker", "rmi", img], acceptable_returncodes={0, 1})
            except SystemExit:
                LOGGER.warning(
                    "Failed to remove image %s during pruning; continuing", img
                )


def should_publish_github_release() -> bool:
    """Return whether GitHub Releases publication is enabled.

    Returns:
        True if GitHub Release publishing is enabled, False if it is skipped.
    """
    return not env_truthy("SKIP_GITHUB_RELEASE")


def get_github_repository() -> str | None:
    """Return the GitHub repository slug for the current project if available.

    Returns:
        The GitHub repository slug in the form `owner/repo`, or `None` if it
        cannot be determined.
    """
    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    if repository:
        if re.fullmatch(r"[^/]+/[^/]+", repository):
            return repository
        LOGGER.warning("Ignoring invalid GITHUB_REPOSITORY value: %s", repository)

    result = run_command(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        acceptable_returncodes={0, 128},
    )
    if result.returncode != 0:
        return None

    remote_url = result.stdout.strip()
    if not remote_url:
        return None

    for pattern in (
        r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$",
        r"^ssh://git@github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$",
        r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
    ):
        match = re.match(pattern, remote_url)
        if match:
            return f"{match.group('owner')}/{match.group('repo')}"

    return None


def get_github_token() -> str | None:
    """Return the GitHub token used for API requests.

    Returns:
        The GitHub token from `GITHUB_TOKEN` or `GH_TOKEN`, or `None` if unset.
    """
    return (os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or "").strip() or None


def get_github_api_base_url() -> str:
    """Return the GitHub API base URL.

    Returns:
        The base URL for GitHub API requests, defaulting to GitHub.com API or
        GitHub Enterprise API if configured.
    """
    api_url = os.getenv("GITHUB_API_URL", "").strip()
    if api_url:
        return api_url.rstrip("/")

    server_url = (
        os.getenv("GITHUB_SERVER_URL", "https://github.com").strip().rstrip("/")
    )
    if server_url.endswith("github.com"):
        return "https://api.github.com"
    return f"{server_url}/api/v3"


def get_github_upload_api_base_url() -> str:
    """Return the GitHub upload API base URL.

    For GitHub.com uploads, this is a dedicated uploads host. For Enterprise
    installations, use the same API base URL.
    """
    api_base = get_github_api_base_url()
    if api_base == "https://api.github.com":
        return "https://uploads.github.com"
    return api_base


class GitHubClient:
    """Encapsulate GitHub API and upload request behavior."""

    def __init__(self, repository: str | None = None, token: str | None = None):
        self.repository = repository or get_github_repository()
        self.token = token or get_github_token()

    @property
    def is_available(self) -> bool:
        return self.repository is not None and self.token is not None

    def _build_headers(self, content_type: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "common-python-tasks",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if content_type is not None:
            headers["Content-Type"] = content_type
        return headers

    def _build_url(self, path: str, upload: bool = False) -> str:
        base_url = (
            get_github_upload_api_base_url() if upload else get_github_api_base_url()
        )
        return f"{base_url}/repos/{self.repository}{path}"

    def _request(
        self,
        method: str,
        path: str,
        payload: bytes | None = None,
        upload: bool = False,
        content_type: str | None = None,
        allow_404_release_tag: bool = False,
    ) -> dict[str, Any] | None:
        if self.repository is None:
            return None
        if self.token is None:
            if upload:
                fatal(
                    "GITHUB_TOKEN or GH_TOKEN environment variable must be set to publish GitHub Release assets"
                )
            return None

        request = urllib.request.Request(
            self._build_url(path, upload=upload),
            data=payload,
            method=method,
            headers=self._build_headers(content_type),
        )

        try:
            with urllib.request.urlopen(request) as response:
                body = response.read().decode("utf-8").strip()
        except urllib.error.HTTPError as exc:
            if (
                allow_404_release_tag
                and method == "GET"
                and exc.code == 404
                and path.startswith("/releases/tags/")
            ):
                return None
            raise

        if not body:
            return None
        return json.loads(body)

    def api_request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        allow_404_release_tag: bool = False,
    ) -> dict[str, Any] | None:
        request_payload = (
            None if payload is None else json.dumps(payload).encode("utf-8")
        )
        content_type = "application/json" if payload is not None else None
        return self._request(
            method,
            path,
            payload=request_payload,
            upload=False,
            content_type=content_type,
            allow_404_release_tag=allow_404_release_tag,
        )

    def upload_request(
        self,
        method: str,
        path: str,
        payload: bytes | None = None,
        content_type: str | None = None,
    ) -> dict[str, Any] | None:
        if content_type is None and payload is not None:
            content_type = "application/octet-stream"
        return self._request(
            method,
            path,
            payload=payload,
            upload=True,
            content_type=content_type,
        )


def github_api_request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Perform a GitHub API request and return the decoded JSON response.

    Args:
        method: HTTP method (e.g. `GET`, `POST`, `PATCH`).
        path: API path relative to `/repos/{owner}/{repo}`.
        payload: Optional JSON-serialisable request body.

    Returns:
        Parsed JSON response body, or `None` if there is no body or the
        required credentials are unavailable.
    """
    return GitHubClient().api_request(method, path, payload=payload)


def publish_github_release(
    tag_name: str,
    release_name: str | None = None,
    body: str | None = None,
    prerelease: bool = False,
    draft: bool = False,
    assets: list[Path | str] | None = None,
) -> dict[str, Any] | None:
    """Create or update a GitHub Release for the given tag.

    Args:
        tag_name: Git tag name for this release.
        release_name: Display name of the release. Defaults to `tag_name`.
        body: Release description text. Defaults to `Release {tag_name}`.
        prerelease: Mark the release as a pre-release.
        draft: Mark the release as a draft.
        assets: Optional list of paths to upload as release assets.

    Returns:
        The GitHub API response for the created or updated release, or `None`
        when publication is disabled or credentials are unavailable.
    """
    if not should_publish_github_release():
        LOGGER.debug(
            "Skipping GitHub Release publication because SKIP_GITHUB_RELEASE is set"
        )
        return

    repository = get_github_repository()
    token = get_github_token()
    if repository is None:
        LOGGER.debug(
            "Skipping GitHub Release publication because this is not a GitHub repository"
        )
        return None
    if token is None:
        fatal(
            "GITHUB_TOKEN or GH_TOKEN environment variable must be set to publish GitHub Release"
        )

    release_name = release_name or tag_name
    release_body = body if body is not None else f"Release {tag_name}"
    payload = {
        "tag_name": tag_name,
        "name": release_name,
        "body": release_body,
        "draft": draft,
        "prerelease": prerelease,
    }

    client = GitHubClient(repository=repository, token=token)
    encoded_tag_name = urllib.parse.quote(tag_name, safe="")
    existing_release = client.api_request(
        "GET",
        f"/releases/tags/{encoded_tag_name}",
        allow_404_release_tag=True,
    )
    if existing_release and isinstance(existing_release.get("id"), int):
        LOGGER.info("Updating GitHub Release for tag %s", tag_name)
        release = client.api_request(
            "PATCH",
            f"/releases/{existing_release['id']}",
            payload=payload,
        )
    else:
        LOGGER.info("Creating GitHub Release for tag %s", tag_name)
        release = client.api_request("POST", "/releases", payload=payload)

    if assets is None:
        assets = get_github_release_asset_paths()
    assets_to_upload = [
        Path(asset) if not isinstance(asset, Path) else asset for asset in assets
    ]
    if assets_to_upload:
        if release is None or not isinstance(release.get("id"), int):
            fatal("GitHub Release was not created successfully; cannot upload assets.")
        upload_github_release_assets(release["id"], assets_to_upload)
    else:
        LOGGER.info("No GitHub Release assets found to upload for tag %s", tag_name)

    return release


def github_upload_request(
    method: str,
    path: str,
    payload: bytes | None = None,
    content_type: str | None = None,
) -> dict[str, Any] | None:
    """Perform a GitHub upload request and return the decoded JSON response."""
    return GitHubClient().upload_request(
        method,
        path,
        payload=payload,
        content_type=content_type,
    )


def get_github_release_asset_paths(asset_sources: str | None = None) -> list[Path]:
    """Return asset paths to upload for a GitHub Release.

    Args:
        asset_sources: Optional colon-separated list of paths or glob patterns.
            If not provided, the default value is `dist/*`.

    Returns:
        A sorted list of existing asset paths.
    """
    sources = (
        asset_sources
        if asset_sources is not None
        else os.getenv("GITHUB_RELEASE_ASSETS", "dist/*")
    )
    explicit_assets = asset_sources is not None or os.getenv("GITHUB_RELEASE_ASSETS")

    asset_paths: list[Path] = []
    for part in (p.strip() for p in sources.split(":") if p.strip()):
        if any(char in part for char in "*?[]"):
            asset_paths.extend(
                sorted(
                    [path for path in Path(".").glob(part) if path.is_file()],
                    key=lambda p: str(p),
                )
            )
            continue

        path = Path(part)
        if path.is_file():
            asset_paths.append(path)
        elif path.exists():
            LOGGER.warning("Ignoring non-file GitHub release asset path: %s", path)

    if not asset_paths and explicit_assets:
        fatal(
            f"No GitHub Release assets were found for the configured asset paths: {sources}"
        )

    return sorted(dict.fromkeys(asset_paths), key=lambda p: str(p))


def get_github_release_assets(release_id: int) -> list[dict[str, Any]]:
    """Get existing assets for a GitHub Release."""
    return github_api_request("GET", f"/releases/{release_id}/assets") or []


def delete_github_release_asset(asset_id: int) -> None:
    """Delete a GitHub Release asset by ID."""
    github_upload_request("DELETE", f"/releases/assets/{asset_id}")


def upload_github_release_asset(
    release_id: int, asset_path: Path
) -> dict[str, Any] | None:
    """Upload a single asset to a GitHub Release."""
    if not asset_path.is_file():
        fatal("GitHub Release asset not found: %s", asset_path)

    existing_assets = get_github_release_assets(release_id)
    for asset in existing_assets:
        if asset.get("name") == asset_path.name and isinstance(asset.get("id"), int):
            LOGGER.info("Deleting existing GitHub release asset %s", asset_path.name)
            delete_github_release_asset(asset["id"])
            break

    content_type, _ = mimetypes.guess_type(str(asset_path))
    content_type = content_type or "application/octet-stream"
    return github_upload_request(
        "POST",
        f"/releases/{release_id}/assets?name={urllib.parse.quote(asset_path.name, safe='')}",
        payload=asset_path.read_bytes(),
        content_type=content_type,
    )


def upload_github_release_assets(
    release_id: int, asset_paths: list[Path]
) -> list[dict[str, Any]]:
    """Upload multiple assets to a GitHub Release."""
    uploaded_assets: list[dict[str, Any]] = []
    for asset_path in asset_paths:
        LOGGER.info("Uploading GitHub Release asset: %s", asset_path)
        uploaded = upload_github_release_asset(release_id, asset_path)
        if uploaded is not None:
            uploaded_assets.append(uploaded)
    return uploaded_assets


def get_project_version_from_poetry() -> str:
    """Return the project version parsed from `poetry version` output.

    Returns:
        The parsed project version string.
    """
    poetry_version_output = run_command(
        ["poetry", "version"],
        capture_output=True,
        acceptable_returncodes={0},
    ).stdout.strip()
    if not poetry_version_output:
        fatal("Unable to determine project version from poetry version")

    parts = poetry_version_output.rsplit(" ", 1)
    if len(parts) != 2 or not parts[1].strip():
        fatal("Unexpected poetry version output format: " f"{poetry_version_output!r}")
    return parts[1].strip()


def get_release_tag_from_poetry_version() -> str:
    """Return release tag string in `v<version>` form from Poetry metadata.

    Returns:
        The release tag string prefixed with `v`.
    """
    return f"v{get_project_version_from_poetry()}"


def ensure_on_default_branch() -> None:
    """Fail if the current git branch is not the default branch.

    The default branch is discovered from the remote `origin/HEAD` symbolic
    ref when available; otherwise, `main` is used as a safe default.
    """
    result = run_command(
        ["git", "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"],
        capture_output=True,
        acceptable_returncodes={0, 1},
    )

    default_branch = "main"
    if result.returncode == 0 and result.stdout.strip():
        default_branch = result.stdout.strip().rsplit("/", 1)[-1]

    current_branch_result = run_command(
        ["git", "branch", "--show-current"],
        capture_output=True,
        acceptable_returncodes={0},
    )
    current_branch = current_branch_result.stdout.strip()
    if not current_branch:
        fatal(
            "Unable to determine current git branch. "
            "Release may only be run from the repository default branch."
        )

    if current_branch != default_branch:
        fatal(
            "Release may only be run from the default branch. "
            f"Current branch is '{current_branch}'; expected '{default_branch}'."
        )


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

    result = load_data_file(
        "alembic.ini.j2", type_identifier=compose_type, fatal_on_missing=False
    )
    if result is None:
        return None, False

    from jinja2 import Template

    _, template_content = result
    rendered = Template(template_content).render(
        package_name=get_package_name(use_underscores=True),
    )
    alembic_ini_path.write_text(rendered, encoding="utf-8")
    LOGGER.debug("Rendered bundled alembic.ini.j2 to %s", alembic_ini_path)
    return alembic_ini_path, True


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
    import tempfile

    resolved_path = get_config_path(
        env_var_name,
        local_filename,
        data_filename,
        type_identifier=type_identifier,
    )
    if resolved_path is None:
        fatal(f"No configuration rendered for {data_filename}")

    path_obj = Path(resolved_path)
    should_template = render_template or path_obj.suffix == ".j2"

    if should_template:
        from jinja2 import Template

        package_name = get_package_name()
        env_prefix = os.getenv(
            "ENV_PREFIX",
            package_name_to_underscore(package_name.upper()) if package_name else "",
        )
        template_vars = {
            "PACKAGE_NAME": package_name,
            "PACKAGE_UNDERSCORE_NAME": (
                package_name_to_underscore(package_name) if package_name else ""
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
            fatal(f"Failed to parse .env file {path}: {exc}")
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
    """Ensure required secrets exist (generate once and persist to `.env`)."""
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


def get_required_vars_for_files(
    compose_type: str, compose_files: list[Path]
) -> set[str]:
    """Determine required environment variables based on compose files being used.

    Args:
        compose_type: The compose type (e.g., `fastapi`).
        compose_files: List of compose file paths.

    Returns:
        Set of environment variable names needed for the given files
    """
    type_requirements = _COMPOSE_VAR_REQUIREMENTS.get(compose_type, {})
    required_vars: set[str] = set()

    for file_path in compose_files:
        # Extract the base name without path and extension
        # Handle temp files like "compose-base.abc123.yml" -> "compose-base"
        file_name = file_path.name
        # Remove .yml, .yaml extensions
        for ext in (".yml", ".yaml"):
            if file_name.endswith(ext):
                file_name = file_name.removesuffix(ext)
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
        `dict` of environment variables for `docker compose`
    """
    import platform

    package_name = get_package_name()

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
        "PACKAGE_UNDERSCORE_NAME": package_name_to_underscore(package_name),
        "POETRY_VERSION": get_poetry_version(),
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
    compose_files_env = os.getenv("COMPOSE_FILE")
    if compose_files_env:
        LOGGER.debug(
            "Using compose files from environment variable COMPOSE_FILE: %s",
            compose_files_env,
        )
        return (
            [Path(f.strip()) for f in compose_files_env.split(":") if f.strip()],
            [],
            [],
        )

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
        render_file(
            f"{compose_type.upper()}_COMPOSE_BASE",
            "compose-base.yml",
            "compose-base.yml.j2",
            render_template=True,
            type_identifier=compose_type,
            suffix=".yml",
        )
    ]

    # Resolve auxiliary configs needed by addons before rendering addon compose
    # files, so that absolute paths can be passed as template variables.
    temp_config_files: list[Path] = []
    addon_template_vars: dict[str, dict[str, str]] = {}

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
        # Load debug overlays only for addons that were explicitly requested
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
        overlay_files = [f.strip() for f in overlay_files_str.split(":") if f.strip()]
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
        A 4-tuple of (compose_files, temp_compose_files, temp_config_files, compose_env).
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
) -> None:
    """Run `docker compose` with standard file and env-file arguments.

    Python has issues running interactive `docker compose` commands directly (e.g.
    `up`) because of how it handles subprocess I/O and signals, so instead, for
    those, consider using `_build_exec_script`.

    Args:
        *args: Command arguments (None values are filtered out).
        compose_files: List of compose file paths.
        compose_env: Environment variables for the command.
    """
    run_command(
        [
            *compose_cmd_prefix(compose_files),
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
            `["docker", "compose", ..., "rm", "-f", "-s", "-v"]`.

    Returns:
        Absolute path to the temporary script file.
    """
    import tempfile
    from shlex import quote

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


def build(
    has_containers: bool,
    debug: bool = False,
    no_cache: bool = False,
    plain: bool = False,
    single_arch: bool = False,
) -> None:
    """Build the package and optionally the container image.

    Args:
        has_containers: When `True`, also build the Docker image after the
            package.
        debug: Build the debug container image stage.
        no_cache: Pass `--no-cache` to the Docker build command.
        plain: Pass `--progress plain` to the Docker build command.
        single_arch: Build the container for the current host architecture only.
    """
    from common_python_tasks.tasks import build_package

    build_package()
    if has_containers:
        build_image(
            debug=debug,
            no_cache=no_cache,
            plain=plain,
            single_arch=single_arch,
        )


def build_image(
    dockerfile_path: Path | None = None,
    dockerfile_text: str | None = None,
    context_path: Path | None = None,
    debug: bool = False,
    no_cache: bool = False,
    plain: bool = False,
    single_arch: bool = False,
    omit_target: bool = False,
    image_name: str | None = None,
    extra_build_args: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Build a Docker image and return its (version_tag, commit_tag).

    Args:
        dockerfile_path: Path to an existing Dockerfile. Mutually exclusive with
            `dockerfile_text`.
        dockerfile_text: Inline Dockerfile content. Mutually exclusive with
            `dockerfile_path`.
        context_path: Docker build context directory. Defaults to the current
            working directory.
        debug: Build the debug image stage.
        no_cache: Pass `--no-cache` to the Docker build command.
        plain: Pass `--progress plain` to the Docker build command.
        single_arch: Build for a single architecture (current host) instead of
            multi-arch.
        omit_target: Omit the `--target` flag (used for extension builds that
            have no named stage).
        image_name: Override the image name derived from the package name.
        extra_build_args: Additional build arguments to pass to the Docker build.

    Returns:
        A 2-tuple of `(version_tag, commit_tag)` for the built image.
    """
    import platform

    from common_python_tasks.tasks import clean

    dist_path = Path("dist")
    if dist_path.exists() and any(dist_path.iterdir()):
        clean(dist_only=True)

    if context_path is None:
        context_path = Path(".")

    temp_file_path = None
    if dockerfile_path is None:
        if dockerfile_text is None:
            fatal("Either dockerfile_path or dockerfile_text must be provided.")
        import tempfile

        tf = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            prefix="Dockerfile.",
            suffix=".generated",
        )
        temp_file_path = tf.name
        with open(temp_file_path, "w", encoding="utf-8") as f:
            f.write(dockerfile_text)
        dockerfile_path = Path(temp_file_path)

    dockerignore_path = context_path / ".dockerignore"
    temp_dockerignore_created = False
    if not dockerignore_path.exists():
        LOGGER.debug("No .dockerignore found; using built-in .dockerignore")
        builtin_dockerignore_content = load_data_file(".dockerignore")[1]
        dockerignore_path.write_text(builtin_dockerignore_content, encoding="utf-8")
        temp_dockerignore_created = True

    delete_temp_file = False
    try:
        # TODO: Revisit this in regards to more architectures
        archs = ["linux/amd64", "linux/arm64"] if not single_arch else None
        files_to_ignore = [Path(".dockerignore")] if temp_dockerignore_created else []
        version_string = get_image_tag(ignore=files_to_ignore)

        if debug:
            suffix = "-debug"
            target = "debug"
            tag = "debug"
        else:
            suffix = ""
            target = "runtime"
            # Only tag as 'latest' if there are no tags later in history
            tag = "latest" if not has_tags_later_in_history() else None

        version_tag = f"{version_string}{suffix}"
        commit_tag = f"{run_command(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True).stdout.strip()}{'-dirty' if get_dirty_files(ignore=files_to_ignore) else ''}{suffix}"
        python_version = platform.python_version()
        poetry_version = get_poetry_version()

        build_args = {
            k: v
            for k, v in {
                "PYTHON_VERSION": python_version,
                "POETRY_VERSION": poetry_version,
                "POETRY_DYNAMIC_VERSIONING_PLUGIN_VERSION": get_installed_requirement_version(
                    "poetry-dynamic-versioning[plugin]"
                ),
                "POETRY_PLUGIN_EXPORT_VERSION": get_installed_requirement_version(
                    "poetry-plugin-export"
                ),
                "TOMLKIT_VERSION": get_installed_requirement_version("tomlkit"),
                "PACKAGE_NAME": get_package_name(use_underscores=True),
                "AUTHORS": ",".join(
                    [f"{name} <{email}>" for name, email in get_authors()]
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
        image_short_name = image_name if image_name is not None else get_package_name()
        orig_full_name = get_full_image_name()
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
            str(dockerfile_path),
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
        run_command(build_cmd)
        delete_temp_file = True
    finally:
        if temp_file_path is not None and delete_temp_file:
            try:
                dockerfile_path.unlink()
            except FileNotFoundError:
                pass
        if temp_dockerignore_created:
            try:
                dockerignore_path.unlink()
            except FileNotFoundError:
                pass
    return version_tag, commit_tag


def build_extension_image(
    base_full_name: str,
    base_version_tag: str,
    extension_content: str,
    context_path: Path | None = None,
    image_name_override: str | None = None,
    debug: bool = False,
    no_cache: bool = False,
    plain: bool = False,
    single_arch: bool = False,
    extra_build_args: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Build an image that starts `FROM` the primary image and returns its tags.

    The created Dockerfile will begin with `FROM {base_full_name}:{base_version_tag}`
    followed by the provided extension content.

    Args:
        base_full_name: Full name of the base image (e.g. `docker.io/org/app`).
        base_version_tag: Tag of the base image to extend.
        extension_content: Dockerfile content appended after the `FROM` line.
        context_path: Docker build context directory. Defaults to `.`.
        image_name_override: Override the image name for the extension image.
        debug: Build the debug image stage.
        no_cache: Pass `--no-cache` to the Docker build command.
        plain: Pass `--progress plain` to the Docker build command.
        single_arch: Build for the current host architecture only.
        extra_build_args: Additional build arguments to pass to the Docker build.

    Returns:
        A 2-tuple of `(version_tag, commit_tag)` for the built extension image.
    """
    if context_path is None:
        context_path = Path(".")

    LOGGER.debug(
        "Building extension image based on %s:%s with override name '%s'",
        base_full_name,
        base_version_tag,
        image_name_override,
    )
    return build_image(
        dockerfile_path=None,
        dockerfile_text=(
            f"FROM {base_full_name}:{base_version_tag}\n\n{extension_content}\n"
        ),
        context_path=context_path,
        debug=debug,
        no_cache=no_cache,
        plain=plain,
        single_arch=single_arch,
        omit_target=True,
        image_name=image_name_override or get_package_name(),
        extra_build_args=extra_build_args,
    )
