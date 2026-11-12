import os
from pathlib import Path
from typing import NamedTuple

from ._task_registry import LOGGER, tasks


class _ContainerBuild(NamedTuple):
    """Artifacts created by a container build task."""

    dockerfile_text: str
    version_tag: str
    commit_tag: str


def _prune_container_images(version_tag: str, commit_tag: str) -> None:
    from .docker import prune_images_keep
    from .env import get_prune_keep
    from .utils import get_full_image_name, get_package_name

    keep = get_prune_keep()
    if keep < 0:
        return

    LOGGER.debug(
        "Pruning old images; keeping %d and protecting tags: %s",
        keep,
        [version_tag, commit_tag],
    )
    prune_images_keep(
        get_full_image_name(),
        get_package_name(),
        keep,
        protect_tags=[version_tag, commit_tag],
    )


def _get_container_build_setting(name: str) -> str:
    return os.getenv(name, "").strip()


@tasks.script(tags=["containers", "build"])
def build_image(
    *docker_build_options: str,
    debug: bool = False,
    no_cache: bool = False,
    plain: bool = False,
    single_arch: bool = False,
    dockerfile_path: str | None = None,
    dockerfile_hook_path: str | None = None,
    container_env: list[str] | None = None,
    container_envfile: list[str] | None = None,
) -> _ContainerBuild:
    """Build the container image using a project-owned or bundled Dockerfile.

    Args:
        *docker_build_options: Additional options passed directly to `docker build`.
            Provide them after the task's `--` separator. Overrides
            `CONTAINER_DOCKER_BUILD_OPTIONS` when provided.
        debug: Build the debug image.
        no_cache: Do not use cache when building the image.
        plain: Do not pretty-print output.
        single_arch: Build images for a single architecture.
        dockerfile_path: Optional project-owned Dockerfile. Overrides
            CONTAINER_DOCKERFILE_PATH if provided.
        dockerfile_hook_path: Optional executable script path that can mutate
            the selected Dockerfile before build. Overrides
            CONTAINER_DOCKERFILE_HOOK_PATH if provided.
        container_env: Builder and runtime environment declarations as repeated
            KEY=VALUE values.
        container_envfile: Optional repeated list of files containing builder and runtime
            environment declarations.

    Precedence for container env declarations is: .containerenv, container_envfile,
    CONTAINER_ENV, then container_env. All supported sources are stacked in that order.

    Returns:
        The generated Dockerfile text and image tags.
    """
    from .docker import build_image as _build_image
    from .env import (
        collect_uv_index_credentials,
        get_cache_id_suffix,
        get_container_deps_move_script,
        get_python_variant,
        inject_auto_build_args_from_env,
        load_container_env_tokens,
        parse_container_deps_mappings,
        parse_container_deps_source,
        parse_container_extensions,
        render_container_deps_move_script,
        resolve_container_docker_build_options,
        resolve_container_dockerfile_hook_path,
        resolve_container_dockerfile_path,
        resolve_extension_build_context,
        resolve_extension_content,
        uv_index_secret_build_options,
        uv_index_secret_mounts,
    )
    from .project import (
        has_debug_dependency_group,
        resolve_container_entrypoint_command,
    )
    from .utils import (
        fatal,
        load_data_file,
        render_template_text,
    )

    resolved_dockerfile_path = resolve_container_dockerfile_path(
        dockerfile_path,
        os.getenv("CONTAINER_DOCKERFILE_PATH"),
    )

    # Determine extensions up-front so we can log a single, accurate message
    extensions = [] if resolved_dockerfile_path else parse_container_extensions()
    extension_ids = [desc.get("id") for desc in extensions if desc.get("id")]
    if extension_ids:
        LOGGER.info("Building image (with extensions: %s)", ", ".join(extension_ids))
    else:
        LOGGER.info("Building image")

    # Resolve all extension fragments up-front so we fail fast on missing
    # bundles or files and avoid calling resolution logic multiple times.
    resolved_fragments = [resolve_extension_content(desc) for desc in extensions]
    extension_build_contexts = [
        context
        for desc in extensions
        if (context := resolve_extension_build_context(desc)) is not None
    ]

    resolved_docker_build_options = resolve_container_docker_build_options(
        docker_build_options,
        os.getenv("CONTAINER_DOCKER_BUILD_OPTIONS"),
    )
    uv_credentials = collect_uv_index_credentials()
    if uv_credentials:
        LOGGER.debug(
            "Passing UV index credentials for: %s",
            ", ".join(c["index_name"] for c in uv_credentials),
        )
        resolved_docker_build_options = uv_index_secret_build_options(
            uv_credentials
        ) + list(resolved_docker_build_options)
    resolved_dockerfile_hook_path = resolve_container_dockerfile_hook_path(
        dockerfile_hook_path,
        os.getenv("CONTAINER_DOCKERFILE_HOOK_PATH"),
    )
    top_level_build_args = inject_auto_build_args_from_env(
        {"PYTHON_VARIANT": get_python_variant()}
    )

    if resolved_dockerfile_path:
        version_tag, commit_tag = _build_image(
            dockerfile_path=resolved_dockerfile_path,
            context_path=Path("."),
            debug=debug,
            no_cache=no_cache,
            plain=plain,
            single_arch=single_arch,
            omit_target=not debug,
            extra_build_args=top_level_build_args or None,
            docker_build_options=resolved_docker_build_options,
            dockerfile_hook_path=resolved_dockerfile_hook_path,
        )
        _prune_container_images(version_tag, commit_tag)
        return _ContainerBuild(
            dockerfile_text=resolved_dockerfile_path.read_text(encoding="utf-8"),
            version_tag=version_tag,
            commit_tag=commit_tag,
        )

    has_debug_deps = has_debug_dependency_group()
    if debug and not has_debug_deps:
        fatal(
            "Debug image requested, but no non-empty [dependency-groups].debug was found in pyproject.toml"
        )

    apt_packages = _get_container_build_setting("CONTAINER_APT_PACKAGES")
    if apt_packages:
        LOGGER.debug("Installing container APT packages: %s", apt_packages)
    entrypoint_command = resolve_container_entrypoint_command(
        entrypoint_script=_get_container_build_setting("CONTAINER_CUSTOM_ENTRYPOINT")
    )
    LOGGER.debug("Using container entrypoint command: %s", entrypoint_command)
    container_env_vars = load_container_env_tokens(
        container_env,
        container_envfile,
    )
    if container_env_vars:
        LOGGER.debug(
            "Injecting builder and runtime env vars: %s",
            ", ".join(container_env_vars),
        )
    external_deps_image = _get_container_build_setting("CONTAINER_DEPS_IMAGE")
    if external_deps_image:
        top_level_build_args["CONTAINER_DEPS_IMAGE"] = external_deps_image

    combined_content = ""
    merged_build_args = top_level_build_args or None
    if extensions:
        combined_content = "\n\n".join(
            c for c in [f.rstrip() for f in resolved_fragments] if c
        )
        # Collect extension-specific build-args (convention per-bundle)
        extra_build_args = {}
        import re

        for desc, fragment in zip(extensions, resolved_fragments):
            args_val = desc.get("args")
            if args_val is None:
                continue

            arg_names = re.findall(
                r"^\s*ARG\s+([A-Za-z_][A-Za-z0-9_]*)", fragment, re.MULTILINE
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
        merged_build_args = {**top_level_build_args}
        merged_build_args.update(extra_build_args)

    # Optionally build a dependency collector image
    deps_dockerfile_path, deps_content = parse_container_deps_source()
    deps_mappings = parse_container_deps_mappings()
    if deps_mappings and not (
        deps_content or deps_dockerfile_path or external_deps_image
    ):
        fatal(
            "CONTAINER_DEPS_MAPPINGS is set but no CONTAINER_DEPS_CONTENT, CONTAINER_DEPS_FILE, or CONTAINER_DEPS_IMAGE was provided"
        )

    deps_image_tag = external_deps_image or ""
    container_deps_move_script = get_container_deps_move_script()

    if container_deps_move_script:
        if deps_mappings:
            LOGGER.warning(
                "Both CONTAINER_DEPS_MOVE_SCRIPT(_PATH) and CONTAINER_DEPS_MAPPINGS are set; using CONTAINER_DEPS_MOVE_SCRIPT(_PATH)."
            )
    else:
        container_deps_move_script = render_container_deps_move_script(
            deps_mappings or {}
        )

    if container_deps_move_script:
        LOGGER.debug(
            "Rendered container deps move script:\n%s",
            container_deps_move_script,
        )

    cache_id_suffix = get_cache_id_suffix(no_cache)

    if deps_content or deps_dockerfile_path:
        deps_image_tag = build_deps_image_task(
            *resolved_docker_build_options,
            no_cache=no_cache,
            plain=plain,
            single_arch=single_arch,
        )
        if merged_build_args is None:
            merged_build_args = {}
        merged_build_args["CONTAINER_DEPS_IMAGE"] = deps_image_tag

    dockerfile_text = render_template_text(
        load_data_file("Dockerfile.j2")[1],
        {
            "EXTENSION_CONTENT": combined_content,
            "CONTAINER_DEPS_IMAGE": deps_image_tag,
            "CONTAINER_DEPS_MOVE_SCRIPT": container_deps_move_script,
            "HAS_DEBUG_DEPS": has_debug_deps,
            "CONTAINER_APT_PACKAGES": apt_packages,
            "ENTRYPOINT_COMMAND": entrypoint_command,
            "CONTAINER_ENV_VARS": container_env_vars,
            "CACHE_ID_SUFFIX": cache_id_suffix,
            "UV_INDEX_SECRET_MOUNTS": uv_index_secret_mounts(uv_credentials),
        },
    )

    version_tag, commit_tag = _build_image(
        dockerfile_path=None,
        dockerfile_text=dockerfile_text,
        context_path=Path("."),
        debug=debug,
        no_cache=no_cache,
        plain=plain,
        single_arch=single_arch,
        extra_build_args=merged_build_args or None,
        docker_build_options=[
            *resolved_docker_build_options,
            *(
                item
                for name, path in extension_build_contexts
                for item in ("--build-context", f"{name}={path}")
            ),
        ],
        dockerfile_hook_path=resolved_dockerfile_hook_path,
    )

    _prune_container_images(version_tag, commit_tag)

    return _ContainerBuild(
        dockerfile_text=dockerfile_text,
        version_tag=version_tag,
        commit_tag=commit_tag,
    )


@tasks.script(task_name="build-deps-image", tags=["containers", "build"])
def build_deps_image_task(
    *docker_build_options: str,
    no_cache: bool = False,
    plain: bool = False,
    single_arch: bool = False,
) -> None:
    """Build only the container dependency collector image for this project.

    Args:
        *docker_build_options: Additional options passed directly to `docker build`.
            Provide them after the task's `--` separator. Overrides
            `CONTAINER_DOCKER_BUILD_OPTIONS` when provided.
        no_cache: Do not use cache when building the deps image.
        plain: Do not pretty-print output.
        single_arch: Build images for a single architecture.

    Returns:
        The full dependency image tag.
    """
    from .docker import build_deps_image
    from .env import (
        get_cache_id_suffix,
        inject_auto_build_args_from_env,
        parse_container_deps_source,
        resolve_container_docker_build_options,
    )
    from .utils import fatal

    deps_dockerfile_path, deps_content = parse_container_deps_source()
    if deps_dockerfile_path is None and deps_content is None:
        fatal(
            "No container dependency source found. Set CONTAINER_DEPS_CONTENT or CONTAINER_DEPS_FILE."
        )

    resolved_docker_build_options = resolve_container_docker_build_options(
        docker_build_options,
        os.getenv("CONTAINER_DOCKER_BUILD_OPTIONS"),
    )
    extra_build_args = inject_auto_build_args_from_env({})
    cache_id_suffix = get_cache_id_suffix(no_cache)

    LOGGER.info("Building container dependency image")
    return build_deps_image(
        deps_content=deps_content,
        deps_dockerfile_path=deps_dockerfile_path,
        context_path=Path("."),
        no_cache=no_cache,
        plain=plain,
        single_arch=single_arch,
        extra_build_args=extra_build_args or None,
        docker_build_options=resolved_docker_build_options,
        cache_id_suffix=cache_id_suffix,
    )


@tasks.script(tags=["containers"])
def run_container(
    tag: str | None = None,
    entrypoint: str | None = None,
    command: str | None = None,
    root: bool = False,
    echo_env: bool = False,
    env: list[str] | None = None,
    envfile: list[str] | None = None,
    privileged: bool = False,
    volumes: list[str] | None = None,
) -> None:
    """Run the Docker image as a container for this project.

    By default, this will run the most-recently-built tag for the project's image.

    Args:
        tag: Image tag to run. Default: Use the most-recently-built tag.
        entrypoint: Optional entrypoint override.
        command: Optional command to pass to the entrypoint.
        root: Whether to run as root (only relevant with a shell entrypoint).
        echo_env: Whether to prepend an env dump to the command.
        env: Repeated KEY=VALUE or KEY values to pass with -e.
        envfile: Repeated envfile paths to pass with --env-file.
        privileged: Whether to run the container with --privileged.
        volumes: Repeated volume mounts to pass with -v.
    """
    from .utils import (
        compose_image_name,
        fatal,
        get_full_image_name,
        get_package_name,
        parse_image_reference,
        run_command,
    )

    package_name = get_package_name()
    if not package_name:
        fatal("PACKAGE_NAME could not be resolved")

    full_name = get_full_image_name()
    parsed_full_name = parse_image_reference(full_name)
    full_repo_name = compose_image_name(
        package_name,
        registry=parsed_full_name["registry"],
        namespace=parsed_full_name["namespace"],
        fully_qualified=True,
    )
    short_repo_name = compose_image_name(package_name, fully_qualified=False)
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
        for candidate in (
            compose_image_name(package_name, tag=tag, fully_qualified=False),
            compose_image_name(
                package_name,
                tag=tag,
                registry=parsed_full_name["registry"],
                namespace=parsed_full_name["namespace"],
                fully_qualified=True,
            ),
        ):
            if _image_exists(candidate):
                selected_image = candidate
                break
        if selected_image is None:
            # Not found locally — assume full name (allow docker to pull if needed)
            selected_image = compose_image_name(
                package_name,
                tag=tag,
                registry=parsed_full_name["registry"],
                namespace=parsed_full_name["namespace"],
                fully_qualified=True,
            )
    else:
        # Find the most-recently-built tag (newest first) for the image
        for repo in (full_repo_name, short_repo_name):
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

    LOGGER.debug("Running container %s", selected_image)
    run_args = ["docker", "run", "--rm", "-i", "-t"]
    if privileged:
        run_args.append("--privileged")
    if env:
        for env_token in env:
            run_args.extend(["-e", env_token])
    if envfile:
        for envfile_path in envfile:
            run_args.extend(["--env-file", envfile_path])
    if volumes:
        for volume in volumes:
            run_args.extend(["-v", volume])
    if entrypoint:
        run_args.extend(["--entrypoint", entrypoint])
    if root:
        run_args.extend(["--user", "root"])
    run_args.append(selected_image)
    if command is not None:
        wrapped_command = (
            (
                "echo '=== Container environment variables ===' && env | sort && echo '========================================' && exec "
                + command
            )
            if echo_env and command
            else command
        )
        run_args.extend(["-c", wrapped_command])

    run_command(run_args)


@tasks.script(tags=["containers", "packaging", "release"])
def push_image(debug: bool = False) -> None:
    """Push the Docker image for this project to the container registry.

    Args:
        debug: Push the debug image.
    """
    from .git import (
        get_image_tag,
        has_tags_later_in_history,
    )
    from .utils import (
        compose_image_name,
        get_full_image_name,
        parse_image_reference,
        run_command,
    )

    if debug:
        suffix = "-debug"
        tag = "debug"
    else:
        suffix = ""
        # Only push 'latest' tag if there are no tags later in history
        tag = "latest" if not has_tags_later_in_history() else None
    parsed_full_name = parse_image_reference(get_full_image_name())
    tags_to_push = [t for t in [tag, f"{get_image_tag()}{suffix}"] if t is not None]
    for t in tags_to_push:
        full_tag = compose_image_name(
            parsed_full_name["repository"],
            tag=t,
            registry=parsed_full_name["registry"],
            namespace=parsed_full_name["namespace"],
            fully_qualified=True,
        )
        LOGGER.info("Pushing image %s", full_tag)
        run_command(["docker", "push", full_tag])


@tasks.script(tags=["containers", "debug"])
def container_shell(
    tag: str | None = None,
    shell: str | None = None,
    root: bool = False,
    no_echo_env: bool = False,
    env: list[str] | None = None,
    envfile: list[str] | None = None,
    privileged: bool = False,
    volumes: list[str] | None = None,
) -> None:
    """Run the debug image with an interactive shell.

    Args:
        tag: Image tag to use. Default: Use the most-recently-built tag.
        shell: Preferred shell name or path. Default: Use the first available from zsh,
            fish, ksh, bash, and sh.
        root: Whether to run the shell as root.
        no_echo_env: Whether to suppress printing environment variables on startup for debugging.
        env: Repeated KEY=VALUE or KEY values to pass with -e.
        envfile: Repeated envfile paths to pass with --env-file.
        privileged: Whether to run the container with --privileged.
        volumes: Repeated volume mounts to pass with -v.
    """
    from shlex import quote

    shell_candidates = (
        ["zsh", "fish", "ksh", "bash", "sh"] if shell is None else [shell]
    )

    run_container(
        tag,
        entrypoint="/bin/sh",
        command=(
            "$("
            + " || ".join(
                f"command -v {quote(candidate)}" for candidate in shell_candidates
            )
            + ") || exit 127"
        ),
        root=root,
        echo_env=not no_echo_env,
        env=env,
        envfile=envfile,
        privileged=privileged,
        volumes=volumes,
    )
