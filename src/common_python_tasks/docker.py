import hashlib
import logging
import platform
import re
import tempfile
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Sequence

from . import git, project, utils
from .env import get_cache_id_suffix, get_workdir_path

LOGGER = logging.getLogger(__name__)


class PruneKeep(IntEnum):
    """Special keep values for image pruning behavior."""

    DISABLED = -1


class DockerPlatform(StrEnum):
    """Supported Docker target platforms for multi-arch builds."""

    AMD64 = "linux/amd64"
    ARM64 = "linux/arm64"


class BuildStage(StrEnum):
    """Named Docker build stages used by image builders."""

    RUNTIME = "runtime"
    DEBUG = "debug"


class BuildTag(StrEnum):
    """Reserved tags managed by image build helpers."""

    LATEST = "latest"
    DEBUG = "debug"


class BuildSuffix(StrEnum):
    """Suffixes appended to version and commit image tags."""

    NONE = ""
    DEBUG = "-debug"


def _resolve_context_path(context_path: Path | None) -> Path:
    return context_path if context_path is not None else Path(".")


def _resolve_archs(single_arch: bool) -> list[DockerPlatform] | None:
    return None if single_arch else [DockerPlatform.AMD64, DockerPlatform.ARM64]


def _merge_build_args(
    base_build_args: dict[str, str | None],
    extra_build_args: dict[str, str] | None = None,
) -> dict[str, str]:
    build_args = {k: v for k, v in base_build_args.items() if v is not None}
    if extra_build_args is not None:
        build_args.update({k: v for k, v in extra_build_args.items() if v is not None})
    return build_args


def _create_temp_dockerfile(
    dockerfile_text: str,
    prefix: str,
) -> tuple[Path, str]:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        delete=False,
        prefix=prefix,
        suffix=".generated",
    ) as temp_file:
        temp_file.write(dockerfile_text)
        temp_file_path = temp_file.name

    return Path(temp_file_path), temp_file_path


def _safe_unlink(path: Path | str | None) -> None:
    if path is None:
        return

    try:
        Path(path).unlink()
    except FileNotFoundError:
        pass


def _build_docker_build_command(
    *,
    context_path: Path,
    dockerfile_path: Path,
    build_args: dict[str, str],
    archs: list[DockerPlatform] | None,
    no_cache: bool,
    plain: bool,
    target: BuildStage | None = None,
    tags: Sequence[str] | None = None,
) -> list[str]:
    build_cmd = [
        "docker",
        "build",
        str(context_path),
        "-f",
        str(dockerfile_path),
    ]
    if target is not None:
        build_cmd += ["--target", target]

    build_cmd += [
        item for k, v in build_args.items() for item in ("--build-arg", f"{k}={v}")
    ]
    if archs:
        build_cmd += ["--platform", ",".join(archs)]
    if no_cache:
        build_cmd += ["--no-cache", "--pull"]
    if tags is not None:
        for tag in tags:
            build_cmd += ["-t", tag]
    if plain:
        build_cmd += ["--progress", "plain"]

    return build_cmd


def prune_images_keep(
    full_name: str,
    package_name: str,
    keep: PruneKeep,
    protect_tags: Sequence[str] | None = None,
) -> None:
    """Prune images for `full_name` keeping the most-recent `keep + 1` images.

    Args:
        full_name: The full image name (including registry and repository) to prune, e.g. `ghcr.io/myorg/myimage`.
        package_name: The name of the package (repository) to prune, e.g. `myimage`.
        keep: The number of most-recent images to keep. Use
            `PruneKeep.DISABLED` to skip pruning.
        protect_tags: A list of tags to protect from pruning.
    """

    if keep <= PruneKeep.DISABLED:
        return
    if protect_tags is None:
        protect_tags = []

    retain_count = int(keep) + 1

    res = utils.run_command(
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
                utils.run_command(["docker", "rmi", img], acceptable_returncodes={0, 1})
            except SystemExit:
                LOGGER.warning(
                    "Failed to remove image %s during pruning; continuing", img
                )


def build_deps_image(
    deps_content: str | None = None,
    deps_dockerfile_path: Path | list[Path] | None = None,
    context_path: Path | None = None,
    no_cache: bool = False,
    plain: bool = False,
    single_arch: bool = False,
    extra_build_args: dict[str, str] | None = None,
    cache_id_suffix: str = "",
) -> str:
    """Build the dependency collector image and return its full tag.

    Args:
        deps_content: The content to use for the dependencies Dockerfile. If provided, this will be rendered into a template Dockerfile.
        deps_dockerfile_path: A path or list of paths to Dockerfile(s) to use for the dependencies image. If multiple paths are provided, their contents will be concatenated. If provided, this takes precedence over `deps_content`.
        context_path: The build context path for the Docker build. Defaults to the current directory.
        no_cache: If `True`, build the image without using cache.
        plain: If `True`, use plain output mode for the Docker build.
        single_arch: If `True`, build the image for the current host architecture only.
        extra_build_args: Additional build arguments for the Docker build as a dictionary of `KEY: VALUE` pairs.
        cache_id_suffix: A suffix to append to the cache ID.

    Returns:
        The full tag of the built dependency image.
    """

    context_path = _resolve_context_path(context_path)

    deps_image_name = f"{utils.get_package_name()}-deps"
    if deps_content is not None and deps_dockerfile_path is not None:
        utils.fatal(
            "build_deps_image may only receive one of deps_content or deps_dockerfile_path"
        )

    if no_cache and not cache_id_suffix:
        cache_id_suffix = get_cache_id_suffix(True)

    if deps_dockerfile_path is not None:
        dockerfile_paths = (
            deps_dockerfile_path
            if isinstance(deps_dockerfile_path, list)
            else [deps_dockerfile_path]
        )
        for path in dockerfile_paths:
            if not path.exists():
                utils.fatal(f"Deps Dockerfile not found: {path}")
        hash_source = "\n".join(
            path.read_text(encoding="utf-8").strip() for path in dockerfile_paths
        )
    elif deps_content is not None:
        hash_source = deps_content
    else:
        utils.fatal(
            "build_deps_image requires either deps_content or deps_dockerfile_path"
        )

    content_hash = hashlib.sha256(hash_source.encode()).hexdigest()[:12]
    deps_tag = f"deps-{content_hash}"

    temp_file_path = None
    if deps_dockerfile_path is None:
        dockerfile_text = utils.render_template_text(
            utils.load_data_file("Dockerfile.deps.j2")[1],
            {"DEPS_CONTENT": deps_content},
        )
        dockerfile_path, temp_file_path = _create_temp_dockerfile(
            dockerfile_text,
            prefix="Dockerfile.deps.",
        )
    else:
        if isinstance(deps_dockerfile_path, list):
            if len(deps_dockerfile_path) == 1:
                dockerfile_path = deps_dockerfile_path[0]
            else:
                dockerfile_text = "\n".join(
                    path.read_text(encoding="utf-8").strip()
                    for path in deps_dockerfile_path
                )
                dockerfile_path, temp_file_path = _create_temp_dockerfile(
                    dockerfile_text,
                    prefix="Dockerfile.deps.",
                )
        else:
            dockerfile_path = deps_dockerfile_path

    python_version = platform.python_version()
    archs = _resolve_archs(single_arch)

    build_args = _merge_build_args(
        {"PYTHON_VERSION": python_version},
        extra_build_args,
    )
    if cache_id_suffix:
        build_args["CACHE_ID_SUFFIX"] = cache_id_suffix

    full_tag = f"{deps_image_name}:{deps_tag}"
    build_cmd = _build_docker_build_command(
        context_path=context_path,
        dockerfile_path=dockerfile_path,
        build_args=build_args,
        archs=archs,
        no_cache=no_cache,
        plain=plain,
        tags=[full_tag],
    )

    LOGGER.info("Building deps image: %s", full_tag)
    try:
        utils.run_command(build_cmd)
    finally:
        _safe_unlink(temp_file_path)

    return full_tag


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
    """Build the primary image and return its version and commit tags.

    Args:
        dockerfile_path: Path to the Dockerfile.
        dockerfile_text: Dockerfile content as a string.
        context_path: Path to the build context.
        debug: If `True`, build the debug image.
        no_cache: If `True`, do not use cache when building the image.
        plain: If `True`, use plain output mode for the Docker build.
        single_arch: If `True`, build the image for the current host architecture only.
        omit_target: If `True`, omit the target stage.
        image_name: Name of the image to build.
        extra_build_args: Additional build arguments for the Docker build as a dictionary of `KEY: VALUE` pairs.

    Returns:
        A tuple containing the version tag and commit tag of the built image.
    """
    dist_path = Path("dist")
    if utils.directory_has_contents(dist_path):
        utils.remove_path(dist_path)

    context_path = _resolve_context_path(context_path)

    temp_file_path = None
    if dockerfile_path is None:
        if dockerfile_text is None:
            utils.fatal("Either dockerfile_path or dockerfile_text must be provided.")
        dockerfile_path, temp_file_path = _create_temp_dockerfile(
            dockerfile_text,
            prefix="Dockerfile.",
        )

    dockerignore_path = context_path / ".dockerignore"
    temp_dockerignore_created = False
    if not dockerignore_path.exists():
        LOGGER.debug("No .dockerignore found; using built-in .dockerignore")
        builtin_dockerignore_content = utils.load_data_file(".dockerignore")[1]
        dockerignore_path.write_text(builtin_dockerignore_content, encoding="utf-8")
        temp_dockerignore_created = True

    delete_temp_file = False
    try:
        archs = _resolve_archs(single_arch)
        files_to_ignore = [Path(".dockerignore")] if temp_dockerignore_created else []
        version_string = git.get_image_tag(ignore=files_to_ignore)

        dockerfile_source = (
            dockerfile_text
            if dockerfile_text is not None
            else dockerfile_path.read_text(encoding="utf-8")
        )
        if (
            debug
            and not omit_target
            and not re.search(
                rf"^\s*FROM\s+\S+\s+AS\s+{BuildStage.DEBUG}\s*$",
                dockerfile_source,
                re.IGNORECASE | re.MULTILINE,
            )
        ):
            utils.fatal(
                "Debug build requested, but the rendered Dockerfile has no debug stage. "
                "Add a non-empty [dependency-groups].debug in pyproject.toml or build without debug."
            )

        if debug:
            suffix = BuildSuffix.DEBUG
            target = BuildStage.DEBUG
            tag = BuildTag.DEBUG
        else:
            suffix = BuildSuffix.NONE
            target = BuildStage.RUNTIME
            tag = BuildTag.LATEST if not git.has_tags_later_in_history() else None

        version_tag = f"{version_string}{suffix}"
        if git.git_available():
            commit_hash = utils.run_command(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                acceptable_returncodes={0},
            ).stdout.strip()
            dirty_suffix = (
                "-dirty" if git.get_dirty_files(ignore=files_to_ignore) else ""
            )
            commit_tag = f"{commit_hash}{dirty_suffix}{suffix}"
        else:
            commit_tag = version_tag

        python_version = platform.python_version()
        poetry_version = project.get_poetry_version()

        build_args = _merge_build_args(
            {
                "PYTHON_VERSION": python_version,
                "POETRY_VERSION": poetry_version,
                "POETRY_DYNAMIC_VERSIONING_PLUGIN_VERSION": project.get_installed_requirement_version(
                    "poetry-dynamic-versioning[plugin]"
                ),
                "POETRY_PLUGIN_EXPORT_VERSION": project.get_installed_requirement_version(
                    "poetry-plugin-export"
                ),
                "TOMLKIT_VERSION": project.get_installed_requirement_version("tomlkit"),
                "PACKAGE_NAME": utils.get_package_name(use_underscores=True),
                "AUTHORS": ",".join(
                    [f"{name} <{email}>" for name, email in project.get_authors()]
                ),
                "GIT_COMMIT": commit_tag,
            },
            extra_build_args,
        )

        build_args.setdefault("WORKDIR_PATH", get_workdir_path())

        tags_to_use = [t for t in (tag, version_tag, commit_tag) if t is not None]
        LOGGER.debug("Building image with tags: %s", ", ".join(tags_to_use))
        image_short_name = (
            image_name if image_name is not None else utils.get_package_name()
        )
        orig_full_name = utils.get_full_image_name()
        if image_name is None:
            image_full_name = orig_full_name
        else:
            if "/" in orig_full_name:
                prefix = orig_full_name.rsplit("/", 1)[0]
                image_full_name = f"{prefix}/{image_name}"
            else:
                image_full_name = image_name
        build_cmd = _build_docker_build_command(
            context_path=context_path,
            dockerfile_path=dockerfile_path,
            build_args=build_args,
            archs=archs,
            no_cache=no_cache,
            plain=plain,
            target=None if omit_target else target,
            tags=[
                *[f"{image_short_name}:{t}" for t in tags_to_use],
                *[f"{image_full_name}:{t}" for t in tags_to_use],
            ],
        )
        utils.run_command(build_cmd)
        delete_temp_file = True
    finally:
        if temp_file_path is not None and delete_temp_file:
            _safe_unlink(dockerfile_path)
        if temp_dockerignore_created:
            _safe_unlink(dockerignore_path)
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
    """Build an image that starts `FROM` the primary image and returns its version and commit tags.

    Args:
        base_full_name: The full name of the base image.
        base_version_tag: The version tag of the base image.
        extension_content: The content to append to the Dockerfile.
        context_path: Path to the build context.
        image_name_override: Override for the image name.
        debug: If `True`, build the debug image.
        no_cache: If `True`, do not use cache when building the image.
        plain: If `True`, use plain output mode for the Docker build.
        single_arch: If `True`, build the image for the current host architecture only.
        extra_build_args: Additional build arguments for the Docker build as a dictionary of `KEY: VALUE` pairs.

    Returns:
        A tuple containing the version tag and commit tag of the built image.
    """

    context_path = _resolve_context_path(context_path)

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
        image_name=image_name_override or utils.get_package_name(),
        extra_build_args=extra_build_args,
    )
