import logging
import os
from pathlib import Path

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
    from common_python_tasks.utils import require_package, run_command

    require_package("black")
    run_command(["black", "--quiet", "."])


@tasks.script(task_name="_isort", tags=["format", "internal"])
def isort() -> None:
    """Run isort formatting."""
    from common_python_tasks.utils import get_config_path, require_package, run_command

    require_package("isort")
    isort_config_path = get_config_path(
        "ISORT_CONFIG",
        ".isort.cfg",
        ".isort.cfg",
        tool_name="isort",
    )

    run_command(
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
    from common_python_tasks.utils import require_package, run_command

    require_package("autoflake")
    run_command(
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
    from common_python_tasks.utils import require_package, run_command

    require_package("black")
    run_command(["black", "--quiet", "--diff", Path("."), "--check"])


@tasks.script(task_name="_isort_check", tags=["lint"])
def isort_check() -> None:
    """Run isort linting."""
    from common_python_tasks.utils import get_config_path, require_package, run_command

    require_package("isort")
    isort_config_path = get_config_path(
        "ISORT_CONFIG",
        ".isort.cfg",
        ".isort.cfg",
        tool_name="isort",
    )

    run_command(
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
    from common_python_tasks.utils import require_package, run_command

    require_package("autoflake")
    run_command(
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
    from common_python_tasks.utils import get_config_path, require_package, run_command

    require_package("flake8")

    flake8_config_path = get_config_path("FLAKE8_CONFIG", ".flake8", ".flake8")

    run_command(["flake8", Path("."), "--config", flake8_config_path])


@tasks.script(tags=["test"])
def test(quiet: bool = False) -> None:
    """Run the test suite with coverage (if `pytest-cov` is installed).


    Args:
        quiet: If `True`, run tests in a quieter mode.
    """
    from common_python_tasks.utils import (
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

    exit_code = run_command(
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
def clean(dist_only: bool = False) -> None:
    """Clean up temporary files and directories.

    Args:
        dist_only: If `True`, only clean the `dist` directory (and related build
            artifacts), leaving other temporary files like `__pycache__` and
            `.pytest_cache` intact.
    """
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
    from common_python_tasks.utils import run_available_tools

    run_available_tools(
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
    from common_python_tasks.utils import run_available_tools

    run_available_tools(
        [
            (autoflake_check, "autoflake"),
            (black_check, "black"),
            (isort_check, "isort"),
            (flake8_check, "flake8"),
        ],
        "No linting tools are installed. Install one or more of: autoflake, black, isort, flake8",
    )


@tasks.script(tags=["containers", "build"])
def build_image(
    debug: bool = False,
    no_cache: bool = False,
    plain: bool = False,
    single_arch: bool = False,
    build_args: str | None = None,
) -> None:
    """Build the container image for this project using the Dockerfile template.

    Args:
        debug: Build the debug image.
        no_cache: Do not use cache when building the image.
        plain: Do not pretty-print output.
        single_arch: Build images for a single architecture.
        build_args: Additional build arguments (format: "KEY=VAL:OTHER=VAL"). Overrides CONTAINER_BUILD_ARGS env var if provided.
    """
    from common_python_tasks.utils import (
        build_extension_image,
        build_image,
        get_full_image_name,
        get_package_name,
        get_prune_keep,
        load_data_file,
        parse_container_extensions,
        prune_images_keep,
        resolve_extension_content,
    )

    # Determine extensions up-front so we can log a single, accurate message
    extensions = parse_container_extensions()
    extension_ids = [desc.get("id") for desc in extensions if desc.get("id")]
    if extension_ids:
        LOGGER.info("Building image (with extensions: %s)", ", ".join(extension_ids))
    else:
        LOGGER.info("Building image")

    # Resolve all extension fragments up-front so we fail fast on missing
    # bundles or files and avoid calling resolution logic multiple times.
    resolved_fragments = [resolve_extension_content(desc) for desc in extensions]

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

    version_tag, commit_tag = build_image(
        dockerfile_path=None,
        dockerfile_text=load_data_file("Dockerfile")[1],
        context_path=Path("."),
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
                    "Extension '%s' provided arguments but its Dockerfile contains no ARG declaration — arguments ignored",
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

        build_extension_image(
            get_full_image_name(),
            version_tag,
            combined_content,
            context_path=Path("."),
            debug=debug,
            no_cache=no_cache,
            plain=plain,
            single_arch=single_arch,
            extra_build_args=merged_build_args or None,
        )

    keep = get_prune_keep()
    if keep >= 0:
        # Protect the tags created by this build
        protect = [t for t in (version_tag, commit_tag) if t is not None]
        LOGGER.debug(
            "Pruning old images; keeping %d and protecting tags: %s", keep, protect
        )
        prune_images_keep(
            get_full_image_name(), get_package_name(), keep, protect_tags=protect
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
    from common_python_tasks.utils import (
        fatal,
        get_full_image_name,
        get_package_name,
        run_command,
    )

    package_name = get_package_name()
    if not package_name:
        fatal("PACKAGE_NAME could not be resolved")

    full_name = get_full_image_name()
    selected_image: str | None = None

    def _image_exists(image: str) -> bool:
        res = run_command(
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
            res = run_command(
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
            fatal(
                f"No local images found for {package_name}. Build the image first or specify a tag."
            )

    LOGGER.info("Running container %s", selected_image)
    run_command(
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
    from common_python_tasks.utils import (
        get_full_image_name,
        get_image_tag,
        has_tags_later_in_history,
        run_command,
    )

    if debug:
        suffix = "-debug"
        tag = "debug"
    else:
        suffix = ""
        # Only push 'latest' tag if there are no tags later in history
        tag = "latest" if not has_tags_later_in_history() else None
    full_name = get_full_image_name()
    tags_to_push = [t for t in [tag, f"{get_image_tag()}{suffix}"] if t is not None]
    for t in tags_to_push:
        full_tag = f"{full_name}:{t}"
        LOGGER.info("Pushing image %s", full_tag)
        run_command(["docker", "push", full_tag])


@tasks.script(task_name="publish-package", tags=["packaging"])
def publish_package(build_first: bool = True) -> None:
    """Publish the package to the PyPI server.

    Args:
        build_first: If `True`, build the package before publishing.
    """
    from common_python_tasks.utils import run_command

    if build_first:
        build_package(clean_dist=True)
    run_command(["poetry", "publish"])


@tasks.script(task_name="publish-github-release", tags=["packaging", "release"])
def publish_github_release(
    tag_name: str | None = None,
    *,
    release_name: str | None = None,
    body: str | None = None,
    prerelease: bool = False,
    draft: bool = False,
    assets: str | None = None,
) -> None:
    """Publish or update a GitHub Release for the current repository."""
    from common_python_tasks.utils import (
        env_truthy,
        fatal,
        get_github_release_asset_paths,
        get_release_tag_from_poetry_version,
    )
    from common_python_tasks.utils import (
        publish_github_release as publish_github_release_helper,
    )

    resolved_tag_name = tag_name or os.getenv("GITHUB_RELEASE_TAG")
    if resolved_tag_name is None:
        resolved_tag_name = get_release_tag_from_poetry_version()
    if not resolved_tag_name:
        fatal("Unable to determine the release tag for GitHub Release publication")

    resolved_release_name = (
        release_name or os.getenv("GITHUB_RELEASE_NAME") or resolved_tag_name
    )
    resolved_body = body or os.getenv("GITHUB_RELEASE_BODY")
    asset_paths = get_github_release_asset_paths(assets)

    return publish_github_release_helper(
        resolved_tag_name,
        release_name=resolved_release_name,
        body=resolved_body,
        prerelease=prerelease or env_truthy("GITHUB_RELEASE_PRERELEASE"),
        draft=draft or env_truthy("GITHUB_RELEASE_DRAFT"),
        assets=asset_paths,
    )


@tasks.script(task_name="build-package", tags=["packaging", "build"])
def build_package(wheel_only: bool = False, clean_dist: bool = False) -> None:
    """Build the package (wheel and sdist)."""
    from common_python_tasks.utils import run_command

    command = ["poetry", "build"]
    if wheel_only:
        command += ["--format", "wheel"]
    if clean_dist:
        dist_path = Path("dist")
        if dist_path.exists() and any(dist_path.iterdir()):
            clean(dist_only=True)
    run_command(command)


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
    from typing import Literal

    from common_python_tasks.utils import (
        fatal,
        get_dirty_files,
        get_project_version_from_poetry,
        run_command,
    )
    from dunamai import Version

    component = component.lower()
    stage = stage.lower() if stage is not None else None

    valid_components = {"major": 0, "minor": 1, "patch": 2}
    if component not in valid_components:
        fatal(f'Invalid component "{component}". Must be one of: major, minor, patch')
    bump_index: Literal[0, 1, 2] = valid_components[component]

    if stage is not None and stage not in {"alpha", "a", "beta", "b", "rc"}:
        fatal(f'Invalid stage "{stage}". Must be one of: alpha, beta, rc')

    if get_dirty_files():
        fatal(
            "Repository has uncommitted changes. "
            "Please commit or stash changes before bumping version."
        )

    bumped = Version.parse(Version.parse(get_project_version_from_poetry()).base).bump(
        bump_index
    )

    if stage is not None:
        bumped.stage = {"a": "alpha", "b": "beta"}.get(stage, stage)
        bumped.revision = 1

    new_version = bumped.serialize()

    if dry_run:
        LOGGER.info("[DRY RUN] Would bump version to %s", new_version)
    else:
        new_tag = f"v{new_version}"
        LOGGER.info("Bumping version to %s", new_version)
        run_command(["git", "tag", new_tag])


@tasks.script(tags=["packaging", "release"])
def release(
    component: str = "patch",
    *,
    stage: str | None = None,
    dry_run: bool = False,
    debug: bool = False,
    no_cache: bool = False,
    plain: bool = False,
    single_arch: bool = False,
    assets: str | None = None,
) -> None:
    """Run a full release flow for package (and containers when included).

    Args:
        component: The version component to bump: `major`, `minor`, or `patch`.
        stage: Optional pre-release stage to apply: `alpha`, `beta`, or `rc`.
        dry_run: If `True`, only perform a dry-run version bump.
        debug: Build/push debug container image tags when releasing containers.
        no_cache: Do not use cache when building container images.
        plain: Do not pretty-print container build output.
        single_arch: Build container image for a single architecture.
    """
    from common_python_tasks.utils import (
        build_image,
        ensure_on_default_branch,
        get_github_release_asset_paths,
        get_release_tag_from_poetry_version,
        is_task_tag_included,
    )
    from common_python_tasks.utils import (
        publish_github_release as publish_github_release_helper,
    )
    from common_python_tasks.utils import (
        run_command,
    )

    normalized_stage = stage
    if normalized_stage is not None and normalized_stage.lower() == "none":
        normalized_stage = None

    ensure_on_default_branch()
    if dry_run:
        LOGGER.info("[DRY RUN] Would clean generated artifacts before release")
    else:
        clean()

    bump_version(component=component, stage=normalized_stage, dry_run=dry_run)
    if dry_run:
        LOGGER.info("[DRY RUN] Would push tags to origin")
        LOGGER.info("[DRY RUN] Would build package with clean_dist=True")
        LOGGER.info("[DRY RUN] Would publish package with build_first=False")
        if is_task_tag_included("containers"):
            LOGGER.info(
                "[DRY RUN] Would build container image with debug=%s no_cache=%s plain=%s single_arch=%s",
                debug,
                no_cache,
                plain,
                single_arch,
            )
            LOGGER.info("[DRY RUN] Would push container image with debug=%s", debug)
        else:
            LOGGER.info(
                "[DRY RUN] Containers tag is not included; would skip image build/push"
            )
        return

    build_package(clean_dist=True)
    publish_package(build_first=False)

    if is_task_tag_included("containers"):
        build_image(
            debug=debug,
            no_cache=no_cache,
            plain=plain,
            single_arch=single_arch,
        )
        push_image(debug=debug)

    release_tag = get_release_tag_from_poetry_version()
    asset_paths = get_github_release_asset_paths(assets)

    run_command(["git", "push", "origin", release_tag])
    try:
        publish_github_release_helper(
            release_tag,
            prerelease=normalized_stage is not None,
            assets=asset_paths,
        )
    except SystemExit:
        LOGGER.warning(
            "GitHub Release publication failed after pushing %s; attempting to remove remote tag",
            release_tag,
        )
        run_command(
            ["git", "push", "origin", "--delete", release_tag],
            acceptable_returncodes={0, 1},
        )
        raise


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
    from common_python_tasks.utils import build

    build(
        has_containers=True,
        debug=debug,
        no_cache=no_cache,
        plain=plain,
        single_arch=single_arch,
    )


@tasks.script(task_name="build", tags=["packaging"])
def build_without_containers() -> None:
    """Build the project."""
    from common_python_tasks.utils import build

    build(has_containers=False)


@tasks.script(task_name="stack-up", tags=["web", "containers", "fastapi"])
def fastapi_stack_up(
    debug: bool = False,
    no_cache: bool = False,
    detach: bool = False,
    services: str | None = None,
) -> None:
    """Bring up the development stack for the application.

    Args:
        debug: Enable debug mode (auto-loads all `*-debug.yml` compose files).
        no_cache: Do not use cache when building the image.
        detach: Run the stack in detached mode.
        services: Optional comma-separated list of services to start
            (e.g. `'api,db'`). If not provided, all services will be started.
    """
    from common_python_tasks.utils import (
        build_exec_script,
        build_image,
        cleanup_temp_files,
        compose_cmd_prefix,
        ensure_secrets_generated,
        exec_script,
        load_and_prepare_compose,
        load_data_file,
        run_docker_compose_command,
    )

    dockerfile_text = load_data_file("Dockerfile")[1]

    commit_tag = build_image(
        None,
        dockerfile_text,
        Path("."),
        debug=debug,
        no_cache=no_cache,
        single_arch=True,
    )[1]

    ensure_secrets_generated()

    compose_files, temp_compose_files, temp_config_files, compose_env = (
        load_and_prepare_compose(
            debug=debug,
            image_tag=commit_tag,
        )
    )
    api_port = int(compose_env["API_PORT"])

    # When watch mode is active, `docker compose` needs the Dockerfile present
    # in the project directory so that watch-triggered rebuilds can find it.
    watch_mode = debug and not detach
    local_dockerfile = Path("Dockerfile")
    wrote_dockerfile = False
    if watch_mode and not local_dockerfile.exists():
        local_dockerfile.write_text(dockerfile_text, encoding="utf-8")
        wrote_dockerfile = True

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
            run_docker_compose_command(
                *up_args,
                compose_files=compose_files,
                compose_env=compose_env,
            )
            LOGGER.info("Application has started! To stop it, run poe stack-down")
        else:
            # Build the full compose command and hand off to an exec'd shell
            # script. This replaces the Python process so that docker compose
            # owns the TTY and signal handling directly
            compose_command = [
                *compose_cmd_prefix(compose_files, tasks),
                *up_args,
            ]

            cleanup_paths: list[Path] = (
                list(temp_compose_files)
                + list(temp_config_files)
                + ([local_dockerfile] if wrote_dockerfile else [])
            )

            teardown_command = [
                *compose_cmd_prefix(compose_files, tasks),
                "rm",
                "-f",
                "-s",
                "-v",
            ]

            script_path = build_exec_script(
                compose_command,
                cleanup_paths=cleanup_paths,
                teardown_command=teardown_command,
            )
            exec_script(script_path, compose_env)
    finally:
        # Only reachable for the detached path (or if exec fails)
        cleanup_temp_files(temp_compose_files)
        if wrote_dockerfile:
            try:
                local_dockerfile.unlink()
            except FileNotFoundError:
                pass


@tasks.script(task_name="stack-down", tags=["web", "containers", "fastapi"])
def fastapi_stack_down() -> None:
    """Bring down the development stack for the application."""
    from common_python_tasks.utils import (
        cleanup_temp_files,
        load_and_prepare_compose,
        run_docker_compose_command,
    )

    compose_files, temp_compose_files, temp_config_files, compose_env = (
        load_and_prepare_compose()
    )

    try:
        LOGGER.info("Bringing down the application stack...")
        run_docker_compose_command(
            "rm",
            "-f",
            "-s",
            "-v",
            compose_files=compose_files,
            compose_env=compose_env,
        )
    finally:
        cleanup_temp_files(temp_compose_files, temp_config_files)


@tasks.script(task_name="reset-db", tags=["web", "containers", "database", "fastapi"])
def fastapi_reset_db() -> None:
    """Reset the database by deleting the database volume."""
    from common_python_tasks.utils import (
        get_package_name,
        load_and_prepare_compose,
        run_command,
    )

    compose_env = load_and_prepare_compose()[3]

    volume_name = f"{get_package_name()}-db-data"
    run_command(
        ["docker", "volume", "rm", "-f", volume_name],
        capture_output=True,
        env=compose_env,
    )


@tasks.script(
    task_name="run-db-migrations", tags=["web", "containers", "database", "fastapi"]
)
def fastapi_run_db_migrations() -> None:
    """Run database migrations."""
    from common_python_tasks.utils import (
        load_and_prepare_compose,
        run_docker_compose_command,
    )

    services = ["db", "migrator"]
    fastapi_stack_up(debug=False, detach=True, services=",".join(services))
    compose_files, _, _, compose_env = load_and_prepare_compose()
    run_docker_compose_command(
        "logs",
        "migrator",
        compose_files=compose_files,
        compose_env=compose_env,
    )
    fastapi_stack_down()


@tasks.script(task_name="db-shell", tags=["web", "containers", "database", "fastapi"])
def fastapi_db_shell() -> None:
    """Open a psql shell to the database container."""
    from common_python_tasks.utils import (
        get_package_name,
        load_and_prepare_compose,
        run_command,
    )

    fastapi_stack_up(debug=False, no_cache=True, detach=True, services="db")
    try:
        compose_files, _, _, compose_env = load_and_prepare_compose()

        run_command(
            [
                "docker",
                "compose",
                *[item for f in compose_files for item in ("-f", str(f))],
                "exec",
                "-it",
                "db",
                "psql",
                "-U",
                os.getenv("DB_USER", get_package_name()),
                os.getenv("DB_BASE", get_package_name()),
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
