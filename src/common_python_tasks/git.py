import logging
import re
import shutil
from enum import StrEnum, auto
from pathlib import Path
from typing import Any, NamedTuple

from dunamai import Style, Version

from . import project, utils

LOGGER = logging.getLogger(__name__)


class NextReleaseVersion(NamedTuple):
    """The computed next release version and normalized component."""

    version: str
    component: str


class ReleaseComponent(StrEnum):
    """Supported semantic version components for release bumps."""

    MAJOR = auto()
    MINOR = auto()
    PATCH = auto()


class ReleaseStage(StrEnum):
    """Supported pre-release stages."""

    ALPHA = auto()
    BETA = auto()
    RC = auto()


def parse_release_component(component: str) -> ReleaseComponent | None:
    """Parse a release component string.

    Args:
        component: The user-provided component string.

    Returns:
        A `ReleaseComponent`, or `None` when `component` is `"auto"`.
    """
    normalized_component = component.lower()
    if normalized_component == "auto":
        return None

    try:
        return ReleaseComponent(normalized_component)
    except ValueError:
        utils.fatal(
            f'Invalid component "{component}". Must be one of: {", ".join((*[member.value for member in ReleaseComponent], "auto"))}.'
        )


def parse_release_stage(stage: str | None) -> ReleaseStage | None:
    """Parse a release stage string.

    Args:
        stage: The user-provided stage string.

    Returns:
        A `ReleaseStage`, or `None` for stable releases.
    """
    if stage is None:
        return None

    normalized_stage = stage.lower()
    if normalized_stage == "none":
        return None
    if normalized_stage == "a":
        return ReleaseStage.ALPHA
    if normalized_stage == "b":
        return ReleaseStage.BETA

    try:
        return ReleaseStage(normalized_stage)
    except ValueError:
        utils.fatal(
            f'Invalid stage "{stage}". Must be one of: alpha, beta, rc or empty for none.'
        )


def compute_next_release_version(
    component: ReleaseComponent | None, stage: ReleaseStage | None
) -> NextReleaseVersion:
    """Compute the next release version based on the given component and stage.

    Args:
        component: The version component to bump, or `None` for auto-inference.
        stage: Optional pre-release stage.

    Returns:
        A `NextReleaseVersion` with the serialized new version and normalized component.
    """
    current_version_text = project.get_project_version()
    release_component = (
        infer_bump_component_from_git_cliff() if component is None else component
    )

    bumped = Version.parse(Version.parse(current_version_text).base).bump(
        list(ReleaseComponent).index(release_component)
    )
    if stage is not None:
        bumped.stage = stage.value
        bumped.revision = 1

    return NextReleaseVersion(
        version=bumped.serialize(), component=release_component.value
    )


def build_release_hook_environment(
    component: ReleaseComponent | None, stage: ReleaseStage | None, dry_run: bool
) -> dict[str, str]:
    """Build the environment variables passed into release hook scripts.

    The following variables are set and available to all hook scripts as environment
    variables:

    - `RELEASE_COMPONENT`: The version component being bumped.
    - `RELEASE_STAGE`: The pre-release stage, or an empty string for a stable release.
    - `RELEASE_VERSION`: The computed next version (e.g. `"1.2.3"`).
    - `RELEASE_TAG`: The Git tag for the release (e.g. `"v1.2.3"`).
    - `RELEASE_DRY_RUN`: `"1"` if this is a dry run, `"0"` otherwise.
    - `RELEASE_SCRIPT_DRY_RUN`: `"1"` if this is a dry run, `"0"` otherwise.
      Hook scripts should check this variable and, when set to `"1"`, log/print
      what they would do without making any changes, then exit successfully.
      This allows the release dry-run to show a complete preview of all
      side effects.

    Args:
        component: The component to bump, or `None` for auto-inference.
        stage: The release stage, or `None` for stable releases.
        dry_run: Whether this is a dry run.

    Returns:
        A dictionary of environment variables for the release hook.
    """
    result = compute_next_release_version(component, stage)
    dry_run_flag = "1" if dry_run else "0"
    return {
        "RELEASE_COMPONENT": result.component,
        "RELEASE_STAGE": stage.value if stage is not None else "",
        "RELEASE_VERSION": result.version,
        "RELEASE_TAG": f"v{result.version}",
        "RELEASE_DRY_RUN": dry_run_flag,
        "RELEASE_SCRIPT_DRY_RUN": dry_run_flag,
    }


def infer_bump_component_from_git_cliff() -> ReleaseComponent:
    """Infer the next semantic version bump type using git-cliff.

    Returns:
        One of `ReleaseComponent.MAJOR`, `ReleaseComponent.MINOR`, or
        `ReleaseComponent.PATCH`.
    """
    if shutil.which("git-cliff") is None:
        utils.fatal(
            "git-cliff is required for auto version bump inference. "
            "Install git-cliff or pass one of: major, minor, patch."
        )

    result = utils.run_git_cliff(
        ["--bumped-version", "--unreleased"], capture_output=True
    )
    version_text = result.stdout.strip()
    if not version_text:
        utils.fatal(
            "git-cliff did not return a bumped version. "
            "Ensure there are unreleased commits and git-cliff is configured correctly."
        )

    normalized_version = version_text.lstrip("v")
    try:
        bumped = Version.parse(normalized_version)
    except Exception:
        utils.fatal(f"Unable to parse bumped version from git-cliff: {version_text!r}")

    current_version = project.get_project_version()
    try:
        current = Version.parse(current_version)
    except Exception:
        utils.fatal(f"Unable to parse current project version: {current_version!r}")

    def _parse_semver(version_value: str | Any) -> tuple[int, int, int]:
        if not isinstance(version_value, str):
            version_value = str(version_value)
        match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version_value)
        if match is None:
            utils.fatal(
                f"Unable to parse semantic version from: {version_value!r}. "
                "Expected a version like X.Y.Z."
            )
        return tuple(int(part) for part in match.groups())

    def _serialize_base(value: Any) -> str:
        return getattr(value, "serialize", lambda: str(value))()

    bumped_major, bumped_minor, bumped_patch = _parse_semver(bumped.base)
    current_major, current_minor, current_patch = _parse_semver(current.base)

    if bumped_major != current_major:
        return ReleaseComponent.MAJOR
    if bumped_minor != current_minor:
        return ReleaseComponent.MINOR
    if bumped_patch != current_patch:
        return ReleaseComponent.PATCH

    utils.fatal(
        "git-cliff did not infer a version change beyond the current version "
        f"{_serialize_base(current.base)!r}; bumped version was {_serialize_base(bumped.base)!r}."
    )


def git_available() -> bool:
    """Return whether Git is installed and the current directory is a repository.

    Returns:
        `True` when Git is available in the current repository.
    """

    if shutil.which("git") is None:
        return False

    result = utils.run_command(
        ["git", "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        acceptable_returncodes={0, 1, 128},
    )
    return result.returncode == 0


def get_dirty_files(ignore: list[Path] | None = None) -> list[Path]:
    """Get dirty git files excluding any specified paths.

    Args:
        ignore: A list of file paths to ignore.

    Returns:
        A list of `Path` objects representing the dirty files.
    """

    if ignore is None:
        ignore = []

    if not git_available():
        return []

    ignore_set = {Path(p) for p in ignore}

    return [
        file_path
        for file_path in [
            Path(line[3:])
            for line in utils.run_command(
                ["git", "status", "--porcelain"], capture_output=True
            ).stdout.splitlines()
            if line
        ]
        if file_path not in ignore_set
    ]


def get_version(ignore: list[Path] | None = None) -> str:
    """Get the current version from git tags, marking dirty when needed.

    Args:
        ignore: Paths to ignore when determining dirty state.

    Returns:
        The current version as a string.
    """
    if ignore is None:
        ignore = []

    if not git_available():
        LOGGER.warning("Git is unavailable. Falling back to placeholder version 0.0.0.")
        return "0.0.0"

    dirty_files = get_dirty_files(ignore=ignore)
    LOGGER.debug("Dirty files: %s", dirty_files)

    return Version.from_git().serialize(
        style=Style.Pep440,
        dirty=bool(dirty_files),
    )


def get_image_tag(ignore: list[Path] | None = None) -> str:
    """Get a version string suitable for use as a Docker image tag.

    Args:
        ignore: Paths to ignore when determining dirty state.

    Returns:
        A normalized version string suitable for Docker tags.
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
    """Check whether any tags are later in history than `HEAD`.

    Returns:
        `True` if tags are later in history, else `False`.
    """

    if not git_available():
        return False

    result = utils.run_command(
        ["git", "tag"],
        capture_output=True,
        acceptable_returncodes={0, 128},
    )
    if result.returncode != 0 or not result.stdout.strip():
        return False

    for tag in result.stdout.strip().split("\n"):
        check_result = utils.run_command(
            ["git", "merge-base", "--is-ancestor", "HEAD", tag],
            capture_output=True,
            acceptable_returncodes={0, 1},
        )
        if check_result.returncode == 1:
            return True

    return False


def get_default_branch() -> str:
    """Return the repository default branch, falling back to `main`.

    Returns:
        The branch named by `origin/HEAD`, or `main` when it is unavailable.
    """
    result = utils.run_command(
        ["git", "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"],
        capture_output=True,
        acceptable_returncodes={0, 1},
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip().rsplit("/", 1)[-1]
    return "main"


def get_current_branch() -> str:
    """Return the currently checked-out branch.

    Returns:
        The current branch name.
    """
    result = utils.run_command(["git", "branch", "--show-current"], capture_output=True)
    current_branch = result.stdout.strip()
    if not current_branch:
        utils.fatal("Unable to determine current git branch.")
    return current_branch


def ensure_on_default_branch() -> None:
    """Fail if the current branch is not the repository default branch."""

    default_branch = get_default_branch()
    current_branch = get_current_branch()

    if current_branch != default_branch:
        utils.fatal(
            "Release may only be run from the default branch. "
            f"Current branch is '{current_branch}'; expected '{default_branch}'."
        )
