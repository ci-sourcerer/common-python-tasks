import os
from pathlib import Path

from ._task_registry import LOGGER, NO_PROMPT_ENV_VAR, tasks
from .utils import confirm


def _should_update_release_changelog() -> bool:
    from .env import env_truthy

    return env_truthy("RELEASE_UPDATE_CHANGELOG")


def _confirm_release_with_uncommitted_changes(dirty_files: list[Path]) -> bool:
    preview = ", ".join(str(path) for path in dirty_files[:5])
    if len(dirty_files) > 5:
        preview = f"{preview}, ... and {len(dirty_files) - 5} more"

    LOGGER.warning("Repository has uncommitted changes: %s", preview)
    return confirm("Proceed with release anyway?")


def _resolve_allow_dirty_release(dirty_files: list[Path]) -> bool:
    from .utils import fatal

    if not dirty_files:
        return False

    if os.getenv(NO_PROMPT_ENV_VAR) == "1":
        LOGGER.warning(
            "Proceeding with release despite uncommitted changes because %s=1",
            NO_PROMPT_ENV_VAR,
        )
        return True

    if _confirm_release_with_uncommitted_changes(dirty_files):
        return True

    fatal("Aborted due to uncommitted changes.")
    return False


def _update_release_changelog(release_tag: str, dry_run: bool = False) -> None:
    from .utils import (
        get_prepended_changelog_contents,
        log_dry_run,
        prepend_changelog,
        run_command,
    )

    changelog_path = Path("CHANGELOG.md")
    if dry_run:
        LOGGER.debug(
            "Dry-run rendered %s contents:\n%s",
            changelog_path,
            get_prepended_changelog_contents(release_tag, changelog_path),
        )
        log_dry_run(
            "Would prepend generated git-cliff release notes for %s to %s",
            release_tag,
            changelog_path,
        )
        run_command(["git", "add", changelog_path], dry_run=True)
        run_command(
            [
                "git",
                "commit",
                "-m",
                f"chore(release): update changelog for {release_tag}",
            ],
            dry_run=True,
        )
        return

    prepend_changelog(release_tag, changelog_path)

    status = run_command(
        ["git", "status", "--porcelain", "--", changelog_path],
        capture_output=True,
    )
    changed_files = (
        status.stdout.strip()
        if status is not None and isinstance(status.stdout, str)
        else ""
    )
    if not changed_files:
        LOGGER.info("CHANGELOG.md already matches release %s", release_tag)
        return

    run_command(["git", "add", changelog_path])
    run_command(
        ["git", "commit", "-m", f"chore(release): update changelog for {release_tag}"]
    )


def _build_and_publish_release_package(
    release_tag: str,
    repository: str | None = None,
    repository_url: str | None = None,
) -> None:
    from .packaging_tasks import build_package, publish_package
    from .utils import run_command

    package_published = False
    try:
        build_package(clean_dist=True)
        publish_package(
            build_first=False,
            repository=repository,
            repository_url=repository_url,
        )
        package_published = True
    finally:
        if not package_published:
            LOGGER.warning(
                "Package build or publication failed; deleting local release tag %s",
                release_tag,
            )
            run_command(
                ["git", "tag", "--delete", release_tag],
                acceptable_returncodes={0, 1},
            )


def _run_release_flow(
    component: str = "auto",
    stage: str | None = None,
    dry_run: bool = False,
    include_containers: bool = False,
    debug: bool = False,
    no_cache: bool = False,
    plain: bool = False,
    single_arch: bool = False,
    dockerfile_path: str | None = None,
    container_env: list[str] | None = None,
    container_envfile: list[str] | None = None,
    assets: list[str] | None = None,
    repository: str | None = None,
    repository_url: str | None = None,
    pre_script: str | None = None,
    post_script: str | None = None,
) -> None:
    from .container_tasks import build_image, push_image
    from .development_tasks import clean
    from .git import (
        build_release_hook_environment,
        ensure_on_default_branch,
        get_dirty_files,
        parse_release_component,
        parse_release_stage,
    )
    from .packaging_tasks import bump_version, publish_github_release
    from .utils import (
        log_dry_run,
        run_command,
    )

    release_component = parse_release_component(component)
    release_stage = parse_release_stage(stage)
    pre_script = pre_script or os.getenv("RELEASE_PRE_SCRIPT")
    post_script = post_script or os.getenv("RELEASE_POST_SCRIPT")

    ensure_on_default_branch()
    allow_dirty = dry_run or _resolve_allow_dirty_release(get_dirty_files())
    hook_env = build_release_hook_environment(release_component, release_stage, dry_run)
    if allow_dirty:
        hook_env[NO_PROMPT_ENV_VAR] = "1"
    if pre_script:
        run_command(["sh", "-lc", pre_script], env=hook_env, dry_run=False)

    if dry_run:
        log_dry_run("Would clean generated artifacts before release")
    else:
        clean()

    if _should_update_release_changelog():
        _update_release_changelog(hook_env["RELEASE_TAG"], dry_run=dry_run)

    # Push all release commits (README, changelog, etc.) before tagging
    if not dry_run:
        run_command(["git", "push", "origin", "HEAD"])

    bump_version(
        component=hook_env["RELEASE_COMPONENT"],
        stage=release_stage.value if release_stage is not None else None,
        dry_run=dry_run,
        allow_dirty=allow_dirty,
    )
    if dry_run:
        log_dry_run("Would push tags to origin")
        log_dry_run("Would build package with clean_dist=True")
        if repository is None and repository_url is None:
            log_dry_run("Would publish package with build_first=False")
        else:
            log_dry_run(
                "Would publish package with build_first=False repository=%s repository_url=%s",
                repository,
                repository_url,
            )
        log_dry_run(
            "Would publish GitHub Release %s with built assets", hook_env["RELEASE_TAG"]
        )
        if include_containers:
            log_dry_run(
                "Would build container image with debug=%s no_cache=%s plain=%s single_arch=%s",
                debug,
                no_cache,
                plain,
                single_arch,
            )
            log_dry_run("Would push container image with debug=%s", debug)
        if post_script:
            run_command(["sh", "-lc", post_script], env=hook_env, dry_run=False)
        return

    _build_and_publish_release_package(
        hook_env["RELEASE_TAG"], repository=repository, repository_url=repository_url
    )

    run_command(["git", "push", "origin", hook_env["RELEASE_TAG"]])
    try:
        publish_github_release(
            hook_env["RELEASE_TAG"],
            prerelease=release_stage is not None,
            assets=assets,
        )
    except SystemExit:
        LOGGER.warning(
            "GitHub Release publication failed after pushing %s; attempting to remove remote tag",
            hook_env["RELEASE_TAG"],
        )
        run_command(
            ["git", "push", "origin", "--delete", hook_env["RELEASE_TAG"]],
            acceptable_returncodes={0, 1},
        )
        raise

    if include_containers:
        build_image(
            debug=debug,
            no_cache=no_cache,
            plain=plain,
            single_arch=single_arch,
            dockerfile_path=dockerfile_path,
            container_env=container_env,
            container_envfile=container_envfile,
        )
        push_image(debug=debug)

    if post_script:
        run_command(["sh", "-lc", post_script], env=hook_env, dry_run=False)


@tasks.script(task_name="release", tags=["packaging", "release", "containers"])
def release(
    component: str = "auto",
    stage: str | None = None,
    dry_run: bool = False,
    debug: bool = False,
    no_cache: bool = False,
    plain: bool = False,
    single_arch: bool = False,
    dockerfile_path: str | None = None,
    container_env: list[str] | None = None,
    container_envfile: list[str] | None = None,
    assets: list[str] | None = None,
    repository: str | None = None,
    repository_url: str | None = None,
    pre_script: str | None = None,
    post_script: str | None = None,
) -> None:
    """Run a full release flow for package and containers.

    Args:
        component: The version component to bump: major, minor, or patch.
        stage: Optional pre-release stage to apply: alpha, beta, or rc.
        dry_run: Only perform a dry-run version bump.
        debug: Build/push debug container image tags when releasing containers.
        no_cache: Do not use cache when building container images.
        plain: Do not pretty-print container build output.
        single_arch: Build container image for a single architecture.
        dockerfile_path: Optional project-owned Dockerfile used for the image
            build. Overrides CONTAINER_DOCKERFILE_PATH if provided.
        container_env: Inline container environment variables as repeated
            KEY=VALUE values.
        container_envfile: Repeated list of container environment files.
        assets: Optional repeated list of release asset patterns or paths.
        repository: Optional configured repository name to publish to.
        repository_url: Optional repository upload URL to publish to.
        pre_script: Optional shell command to run before the release steps.
        post_script: Optional shell command to run after the release completes.
    """
    _run_release_flow(
        component=component,
        stage=stage,
        dry_run=dry_run,
        include_containers=True,
        debug=debug,
        no_cache=no_cache,
        plain=plain,
        single_arch=single_arch,
        dockerfile_path=dockerfile_path,
        container_env=container_env,
        container_envfile=container_envfile,
        assets=assets,
        repository=repository,
        repository_url=repository_url,
        pre_script=pre_script,
        post_script=post_script,
    )


@tasks.script(task_name="release", tags=["packaging", "release", "common"])
def release_without_containers(
    component: str = "auto",
    stage: str | None = None,
    dry_run: bool = False,
    assets: list[str] | None = None,
    repository: str | None = None,
    repository_url: str | None = None,
    pre_script: str | None = None,
    post_script: str | None = None,
) -> None:
    """Run a full release flow for package artifacts without container publishing.

    Args:
        component: The version component to bump: major, minor, or patch.
        stage: Optional pre-release stage to apply: alpha, beta, or rc.
        dry_run: Only perform a dry-run version bump.
        assets: Optional repeated list of release asset patterns or paths.
        repository: Optional configured repository name to publish to.
        repository_url: Optional repository upload URL to publish to.
        pre_script: Optional shell command to run before the release steps.
        post_script: Optional shell command to run after the release completes.
    """
    _run_release_flow(
        component=component,
        stage=stage,
        dry_run=dry_run,
        include_containers=False,
        assets=assets,
        repository=repository,
        repository_url=repository_url,
        pre_script=pre_script,
        post_script=post_script,
    )


def build(
    has_containers: bool,
    debug: bool = False,
    no_cache: bool = False,
    plain: bool = False,
    single_arch: bool = False,
    dockerfile_path: str | None = None,
    container_env: list[str] | None = None,
    container_envfile: list[str] | None = None,
) -> None:
    """Build the package and optionally the container image.

    Args:
        has_containers: When `True`, also build the Docker image after the
            package.
        debug: Build the debug container image stage.
        no_cache: Pass `--no-cache` to the Docker build command.
        plain: Pass `--progress plain` to the Docker build command.
        single_arch: Build the container for the current host architecture only.
        dockerfile_path: Optional project-owned Dockerfile used for the image
            build. Overrides CONTAINER_DOCKERFILE_PATH if provided.
        container_env: Inline container environment variables as repeated
            `KEY=VALUE` values.
        container_envfile: Repeated list of container environment files.
    """
    from .container_tasks import build_image as _build_image
    from .packaging_tasks import build_package

    build_package()
    if has_containers:
        _build_image(
            debug=debug,
            no_cache=no_cache,
            plain=plain,
            single_arch=single_arch,
            dockerfile_path=dockerfile_path,
            container_env=container_env,
            container_envfile=container_envfile,
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
    dockerfile_path: str | None = None,
    container_env: list[str] | None = None,
    container_envfile: list[str] | None = None,
) -> None:
    """Build the project and its containers.

    Args:
        debug: Build the debug image.
        no_cache: Do not use cache when building the image.
        plain: Do not pretty-print output.
        single_arch: Build images for a single architecture.
        dockerfile_path: Optional project-owned Dockerfile used for the image
            build. Overrides CONTAINER_DOCKERFILE_PATH if provided.
        container_env: Inline container environment variables as repeated KEY=VALUE
            values.
        container_envfile: Repeated list of container environment files.
    """

    build(
        True,
        debug=debug,
        no_cache=no_cache,
        plain=plain,
        single_arch=single_arch,
        dockerfile_path=dockerfile_path,
        container_env=container_env,
        container_envfile=container_envfile,
    )


@tasks.script(task_name="build", tags=["packaging", "common"])
def build_without_containers() -> None:
    """Build the project without containers."""

    build(False)
