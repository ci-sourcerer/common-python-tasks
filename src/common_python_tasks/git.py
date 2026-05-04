import re
import shutil
from pathlib import Path
from typing import Any, NamedTuple

from dunamai import Style, Version

from . import project, utils


class NextReleaseVersion(NamedTuple):
    """The computed next release version and normalized component."""

    version: str
    component: str


def compute_next_release_version(
    component: str, stage: str | None
) -> NextReleaseVersion:
    """Compute the next release version based on the given component and stage.

    Args:
        component: The version component to bump (major, minor, patch, or auto).
        stage: Optional pre-release stage (alpha, beta, rc, or None).

    Returns:
        A `NextReleaseVersion` with the serialized new version and normalized component.
    """
    component = component.lower()
    normalized_stage = stage.lower() if stage is not None else None

    current_version_text = project.get_project_version_from_poetry()
    if component == "auto":
        component = infer_bump_component_from_git_cliff()
        if re.match(r"^0\.", str(Version.parse(current_version_text).base)):
            utils.LOGGER.info(
                "Current version %s is pre-production; using patch bump.",
                current_version_text,
            )
            component = "patch"

    valid_components = {"major": 0, "minor": 1, "patch": 2}
    if component not in valid_components:
        utils.fatal(
            f'Invalid component "{component}". Must be one of: {", ".join(valid_components.keys())}.'
        )

    if normalized_stage is not None and normalized_stage not in {
        "alpha",
        "a",
        "beta",
        "b",
        "rc",
    }:
        utils.fatal(
            f'Invalid stage "{normalized_stage}". Must be one of: alpha, beta, rc or empty for none.'
        )

    bumped = Version.parse(Version.parse(current_version_text).base).bump(
        valid_components[component]
    )
    if normalized_stage is not None:
        bumped.stage = {"a": "alpha", "b": "beta"}.get(
            normalized_stage, normalized_stage
        )
        bumped.revision = 1

    return NextReleaseVersion(version=bumped.serialize(), component=component)


def build_release_hook_environment(
    component: str,
    stage: str | None,
    dry_run: bool,
) -> dict[str, str]:
    """Build the environment variables passed into release hook scripts.

    Args:
        component: The component to bump (major, minor, patch, or auto).
        stage: The release stage (alpha, beta, rc, or None).
        dry_run: Whether this is a dry run.

    Returns:
        A dictionary of environment variables for the release hook.
    """
    normalized_stage = stage.lower() if stage is not None else None
    result = compute_next_release_version(component, stage)
    return {
        "RELEASE_COMPONENT": result.component,
        "RELEASE_STAGE": normalized_stage or "",
        "RELEASE_VERSION": result.version,
        "RELEASE_TAG": f"v{result.version}",
        "RELEASE_DRY_RUN": "1" if dry_run else "0",
    }


def infer_bump_component_from_git_cliff() -> str:
    """Infer the next semantic version bump type using git-cliff.

    Returns:
        One of "major", "minor", or "patch".
    """
    if shutil.which("git-cliff") is None:
        utils.fatal(
            "git-cliff is required for auto version bump inference. "
            "Install git-cliff or pass one of: major, minor, patch."
        )

    result = utils.run_command(
        ["git-cliff", "--bumped-version", "--unreleased"],
        capture_output=True,
        acceptable_returncodes={0},
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

    current_version = project.get_project_version_from_poetry()
    try:
        current = Version.parse(current_version)
    except Exception:
        utils.fatal(
            "Unable to parse current version from Poetry output: "
            f"{current_version!r}"
        )

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
        return "major"
    if bumped_minor != current_minor:
        return "minor"
    if bumped_patch != current_patch:
        return "patch"

    utils.fatal(
        "git-cliff did not infer a version change beyond the current version "
        f"{_serialize_base(current.base)!r}; bumped version was {_serialize_base(bumped.base)!r}."
    )


def get_dirty_files(ignore: list[Path] | None = None) -> list[Path]:
    """Get dirty git files excluding any specified paths.

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

    dirty_files = get_dirty_files(ignore=ignore)
    utils.LOGGER.debug("Dirty files: %s", dirty_files)

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


def ensure_on_default_branch() -> None:
    """Fail if the current branch is not the repository default branch."""

    result = utils.run_command(
        ["git", "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"],
        capture_output=True,
        acceptable_returncodes={0, 1},
    )

    default_branch = "main"
    if result.returncode == 0 and result.stdout.strip():
        default_branch = result.stdout.strip().rsplit("/", 1)[-1]

    current_branch_result = utils.run_command(
        ["git", "branch", "--show-current"],
        capture_output=True,
        acceptable_returncodes={0},
    )
    current_branch = current_branch_result.stdout.strip()
    if not current_branch:
        utils.fatal(
            "Unable to determine current git branch. "
            "Release may only be run from the repository default branch."
        )

    if current_branch != default_branch:
        utils.fatal(
            "Release may only be run from the default branch. "
            f"Current branch is '{current_branch}'; expected '{default_branch}'."
        )
