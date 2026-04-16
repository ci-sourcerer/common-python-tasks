import hashlib
import platform
import re
from pathlib import Path
from typing import Sequence

from . import git as _git
from . import project as _project
from . import utils
from .env import get_cache_id_suffix, get_workdir_path


def build(
    has_containers: bool,
    debug: bool = False,
    no_cache: bool = False,
    plain: bool = False,
    single_arch: bool = False,
    build_args: str | None = None,
    container_env: str | None = None,
    container_envfile: str | None = None,
) -> None:
    """Build the package and optionally the container image.

    Args:
        has_containers: When `True`, also build the Docker image after the
            package.
        debug: Build the debug container image stage.
        no_cache: Pass `--no-cache` to the Docker build command.
        plain: Pass `--progress plain` to the Docker build command.
        single_arch: Build the container for the current host architecture only.
        build_args: Additional build arguments for the Docker build.
        container_env: Inline container environment variables.
        container_envfile: Path to a container environment file.
    """
    from common_python_tasks.tasks import build_image as build_container_image
    from common_python_tasks.tasks import build_package

    build_package()
    if has_containers:
        build_container_image(
            debug=debug,
            no_cache=no_cache,
            plain=plain,
            single_arch=single_arch,
            build_args=build_args,
            container_env=container_env,
            container_envfile=container_envfile,
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
    """Build the dependency collector image and return its full tag."""

    if context_path is None:
        context_path = Path(".")

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

        import tempfile

        tf = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            prefix="Dockerfile.deps.",
            suffix=".generated",
        )
        temp_file_path = tf.name
        with open(temp_file_path, "w", encoding="utf-8") as f:
            f.write(dockerfile_text)

        dockerfile_path = Path(temp_file_path)
    else:
        if isinstance(deps_dockerfile_path, list):
            if len(deps_dockerfile_path) == 1:
                dockerfile_path = deps_dockerfile_path[0]
            else:
                dockerfile_text = "\n".join(
                    path.read_text(encoding="utf-8").strip()
                    for path in deps_dockerfile_path
                )
                import tempfile

                tf = tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    delete=False,
                    prefix="Dockerfile.deps.",
                    suffix=".generated",
                )
                temp_file_path = tf.name
                with open(temp_file_path, "w", encoding="utf-8") as f:
                    f.write(dockerfile_text)

                dockerfile_path = Path(temp_file_path)
        else:
            dockerfile_path = deps_dockerfile_path

    python_version = platform.python_version()
    archs = ["linux/amd64", "linux/arm64"] if not single_arch else None

    build_args: dict[str, str] = {"PYTHON_VERSION": python_version}
    if extra_build_args:
        build_args.update({k: v for k, v in extra_build_args.items() if v is not None})
    if cache_id_suffix:
        build_args["CACHE_ID_SUFFIX"] = cache_id_suffix

    full_tag = f"{deps_image_name}:{deps_tag}"
    build_cmd = [
        "docker",
        "build",
        str(context_path),
        "-f",
        str(dockerfile_path),
        *[item for k, v in build_args.items() for item in ("--build-arg", f"{k}={v}")],
        "--platform" if archs else None,
        ",".join(archs) if archs else None,
        "--no-cache" if no_cache else None,
        "--pull" if no_cache else None,
        "-t",
        full_tag,
    ]
    if plain:
        build_cmd += ["--progress", "plain"]

    utils.LOGGER.info("Building deps image: %s", full_tag)
    try:
        utils.run_command(build_cmd)
    finally:
        if temp_file_path is not None:
            try:
                Path(temp_file_path).unlink()
            except FileNotFoundError:
                pass

    return full_tag


def prune_images_keep(
    full_name: str,
    package_name: str,
    keep: int,
    protect_tags: Sequence[str] | None = None,
) -> None:
    """Prune images for `full_name` keeping the most-recent `keep + 1` images."""

    if keep < 0:
        return
    if protect_tags is None:
        protect_tags = []

    retain_count = keep + 1

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
        utils.LOGGER.exception("Failed to list images for pruning: %s", full_name)
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
                utils.LOGGER.info("Pruning image %s", img)
                utils.run_command(["docker", "rmi", img], acceptable_returncodes={0, 1})
            except SystemExit:
                utils.LOGGER.warning(
                    "Failed to remove image %s during pruning; continuing", img
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
    """Build a Docker image and return its `(version_tag, commit_tag)`."""
    from common_python_tasks.tasks import clean

    dist_path = Path("dist")
    if dist_path.exists() and any(dist_path.iterdir()):
        clean(dist_only=True)

    if context_path is None:
        context_path = Path(".")

    temp_file_path = None
    if dockerfile_path is None:
        if dockerfile_text is None:
            utils.fatal("Either dockerfile_path or dockerfile_text must be provided.")
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
        utils.LOGGER.debug("No .dockerignore found; using built-in .dockerignore")
        builtin_dockerignore_content = utils.load_data_file(".dockerignore")[1]
        dockerignore_path.write_text(builtin_dockerignore_content, encoding="utf-8")
        temp_dockerignore_created = True

    delete_temp_file = False
    try:
        archs = ["linux/amd64", "linux/arm64"] if not single_arch else None
        files_to_ignore = [Path(".dockerignore")] if temp_dockerignore_created else []
        version_string = _git.get_image_tag(ignore=files_to_ignore)

        dockerfile_source = (
            dockerfile_text
            if dockerfile_text is not None
            else dockerfile_path.read_text(encoding="utf-8")
        )
        if (
            debug
            and not omit_target
            and not re.search(
                r"^\s*FROM\s+\S+\s+AS\s+debug\s*$",
                dockerfile_source,
                re.IGNORECASE | re.MULTILINE,
            )
        ):
            utils.fatal(
                "Debug build requested, but the rendered Dockerfile has no debug stage. "
                "Add a non-empty [dependency-groups].debug in pyproject.toml or build without debug."
            )

        if debug:
            suffix = "-debug"
            target = "debug"
            tag = "debug"
        else:
            suffix = ""
            target = "runtime"
            tag = "latest" if not _git.has_tags_later_in_history() else None

        version_tag = f"{version_string}{suffix}"
        commit_tag = f"{utils.run_command(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True).stdout.strip()}{'-dirty' if _git.get_dirty_files(ignore=files_to_ignore) else ''}{suffix}"
        python_version = platform.python_version()
        poetry_version = _project.get_poetry_version()

        build_args = {
            k: v
            for k, v in {
                "PYTHON_VERSION": python_version,
                "POETRY_VERSION": poetry_version,
                "POETRY_DYNAMIC_VERSIONING_PLUGIN_VERSION": _project.get_installed_requirement_version(
                    "poetry-dynamic-versioning[plugin]"
                ),
                "POETRY_PLUGIN_EXPORT_VERSION": _project.get_installed_requirement_version(
                    "poetry-plugin-export"
                ),
                "TOMLKIT_VERSION": _project.get_installed_requirement_version(
                    "tomlkit"
                ),
                "PACKAGE_NAME": utils.get_package_name(use_underscores=True),
                "AUTHORS": ",".join(
                    [f"{name} <{email}>" for name, email in _project.get_authors()]
                ),
                "GIT_COMMIT": commit_tag,
            }.items()
            if v is not None
        }
        if extra_build_args:
            for k, v in extra_build_args.items():
                if v is not None:
                    build_args[k] = v

        build_args.setdefault("WORKDIR_PATH", get_workdir_path())

        tags_to_use = [t for t in (tag, version_tag, commit_tag) if t is not None]
        utils.LOGGER.debug("Building image with tags: %s", ", ".join(tags_to_use))
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
            "--pull" if no_cache else None,
            *[item for t in tags_to_use for item in ("-t", f"{image_short_name}:{t}")],
        ]
        for t in tags_to_use:
            build_cmd += ["-t", f"{image_full_name}:{t}"]

        if plain:
            build_cmd += ["--progress", "plain"]
        utils.run_command(build_cmd)
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
    """Build an image that starts `FROM` the primary image and returns its tags."""

    if context_path is None:
        context_path = Path(".")

    utils.LOGGER.debug(
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
