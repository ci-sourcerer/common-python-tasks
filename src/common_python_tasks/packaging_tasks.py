import os
from pathlib import Path

from ._task_registry import LOGGER, tasks


@tasks.script(task_name="publish-package", tags=["packaging", "common"])
def publish_package(
    build_first: bool = True,
    repository: str | None = None,
    repository_url: str | None = None,
) -> None:
    """Publish the package to the PyPI server.

    Args:
        build_first: Build the package before publishing.
        repository: Optional configured repository name to publish to.
        repository_url: Optional repository upload URL to publish to.
    """
    from .project import get_publish_command
    from .utils import run_command

    if build_first:
        build_package(clean_dist=True)
    run_command(
        get_publish_command(repository=repository, repository_url=repository_url)
    )


@tasks.script(
    task_name="publish-github-release", tags=["packaging", "release", "common"]
)
def publish_github_release(
    tag_name: str | None = None,
    release_name: str | None = None,
    body: str | None = None,
    prerelease: bool = False,
    draft: bool = False,
    assets: list[str] | None = None,
) -> None:
    """Publish or update a GitHub Release for the current repository.

    Args:
        tag_name: Optional release tag to publish.
        release_name: Optional display name for the release.
        body: Optional release notes body.
        prerelease: Whether to mark the release as a pre-release.
        draft: Whether to create the release as a draft.
        assets: Optional release asset paths or glob patterns.
    """
    from .env import env_truthy
    from .github import (
        get_github_release_asset_paths,
    )
    from .github import publish_github_release as publish_github_release_helper
    from .project import get_release_tag_from_project_version
    from .utils import fatal

    resolved_tag_name = tag_name or os.getenv("GITHUB_RELEASE_TAG")
    if resolved_tag_name is None:
        resolved_tag_name = get_release_tag_from_project_version()
    if not resolved_tag_name:
        fatal("Unable to determine the release tag for GitHub Release publication")

    resolved_release_name = (
        release_name or os.getenv("GITHUB_RELEASE_NAME") or resolved_tag_name
    )
    resolved_body = body or os.getenv("GITHUB_RELEASE_BODY")
    # Poe supplies an empty list when an optional repeated CLI argument is omitted.
    asset_paths = get_github_release_asset_paths(assets or None)

    return publish_github_release_helper(
        resolved_tag_name,
        release_name=resolved_release_name,
        body=resolved_body,
        prerelease=prerelease or env_truthy("GITHUB_RELEASE_PRERELEASE"),
        draft=draft or env_truthy("GITHUB_RELEASE_DRAFT"),
        assets=asset_paths,
    )


@tasks.script(task_name="build-package", tags=["packaging", "build", "common"])
def build_package(wheel_only: bool = False, clean_dist: bool = False) -> None:
    """Build the package (wheel and sdist).

    Args:
        wheel_only: Whether to build only the wheel artifact.
        clean_dist: Whether to remove existing distribution artifacts first.
    """
    from .development_tasks import clean
    from .project import get_build_command
    from .utils import run_command

    command = get_build_command(wheel_only=wheel_only)
    if clean_dist:
        dist_path = Path("dist")
        if dist_path.exists() and any(dist_path.iterdir()):
            clean(dist_only=True)
    run_command(command)


@tasks.script(tags=["packaging", "common"])
def bump_version(
    component: str = "auto",
    stage: str | None = None,
    dry_run: bool = False,
    allow_dirty: bool = False,
) -> str:
    """Bump the project version.

    Args:
        component: The version component to bump: major, minor, patch, or auto to
            infer the bump from git history using git-cliff.
        stage: Optional pre-release stage to apply: alpha, beta, or rc.
        dry_run: Print what would happen without making changes.
        allow_dirty: Allow version bumping with uncommitted changes.

    Returns:
        The new version string that was/would be set.
    """
    from .git import (
        compute_next_release_version,
        ensure_on_default_branch,
        get_dirty_files,
        parse_release_component,
        parse_release_stage,
    )
    from .utils import (
        fatal,
        log_dry_run,
        run_command,
    )

    ensure_on_default_branch()

    if get_dirty_files() and not allow_dirty:
        fatal(
            "Repository has uncommitted changes. "
            "Please commit or stash changes before bumping version."
        )

    result = compute_next_release_version(
        parse_release_component(component),
        parse_release_stage(stage),
    )
    new_version = result.version

    if dry_run:
        log_dry_run("Would bump version to %s", new_version)
    else:
        LOGGER.info("Bumping version to %s", new_version)
        run_command(["git", "tag", f"v{new_version}"])
    return new_version


@tasks.script(tags=["packaging", "release", "common"])
def changelog() -> None:
    """Print the changelog for the current version based on git history and git-cliff."""
    from .utils import changelog as _changelog

    print(_changelog())
