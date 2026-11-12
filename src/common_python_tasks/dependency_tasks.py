import re
from pathlib import Path

from ._task_registry import LOGGER, tasks


def _dependency_branch_token(name: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", name.lower()).strip("-") or "updates"


def _dependency_update_branch_name(dependency_names: list[str]) -> str:
    if not dependency_names:
        return "deps/update-dependencies"

    branch_name = "deps/" + "-".join(
        _dependency_branch_token(name) for name in dependency_names[:5]
    )
    if len(dependency_names) > 5:
        branch_name = f"{branch_name}-and-more"
    return branch_name[:80].rstrip("-")


def _extract_changed_dependency_names_from_diff(diff_output: str) -> list[str]:
    dependency_names: set[str] = set()
    for line in diff_output.splitlines():
        if not line or line.startswith(("+++", "---", "@@", "diff ", "index ")):
            continue
        if line[0] not in {" ", "+", "-"}:
            continue

        text = line[1:].strip()
        lock_match = re.match(r'name\s*=\s*"([^"]+)"', text)
        if lock_match is not None:
            dependency_names.add(lock_match.group(1))
            continue

        dependency_match = re.match(r'"([A-Za-z0-9_.-]+)(?:\[|\s|[<>=!~;(),"]|$)', text)
        if dependency_match is not None:
            dependency_names.add(dependency_match.group(1))

    return sorted(dependency_names)


def _get_changed_dependency_names() -> list[str]:
    from .utils import run_command

    return _extract_changed_dependency_names_from_diff(
        run_command(
            [
                "git",
                "diff",
                "--unified=3",
                "--",
                "pyproject.toml",
                "uv.lock",
            ],
            capture_output=True,
        ).stdout
    )


def _get_dependency_update_changed_files() -> list[Path]:
    from .utils import run_command

    result = run_command(
        [
            "git",
            "status",
            "--porcelain",
            "--",
            "pyproject.toml",
            "uv.lock",
        ],
        capture_output=True,
    )
    return [Path(line[3:]) for line in result.stdout.splitlines() if line]


def _ensure_clean_dependency_update_worktree() -> None:
    from .git import get_dirty_files
    from .utils import fatal

    if get_dirty_files():
        fatal(
            "Repository has uncommitted changes. "
            "Commit or stash them before creating a dependency update branch, commit, or pull request."
        )


def _dependency_update_title(dependency_names: list[str]) -> str:
    if not dependency_names:
        return "chore(deps): update dependencies"
    if len(dependency_names) == 1:
        return f"chore(deps): update {dependency_names[0]}"
    return "chore(deps): update " + ", ".join(dependency_names[:5])


@tasks.script(task_name="update-dependencies", tags=["packaging", "common"])
def update_dependencies(
    *dependencies: str,
    branch: bool = False,
    branch_name: str | None = None,
    commit: bool = False,
    pr: bool = False,
    draft: bool = False,
    run_tests: bool = False,
) -> None:
    """Update project dependencies with uv.

    Args:
        *dependencies: Optional dependency names to update. When omitted, update
            all dependencies.
        branch: Create a dependency update branch after updating.
        branch_name: Optional branch name to use instead of generating one.
        commit: Commit the dependency update files.
        pr: Create and push a branch, commit the changes, and open a GitHub pull
            request.
        draft: Create the pull request as a draft.
        run_tests: Run the test task before committing.
    """
    from .development_tasks import test
    from .git import get_current_branch, get_default_branch
    from .github import create_pull_request
    from .project import get_dependency_update_command
    from .utils import run_command

    should_create_branch = branch or branch_name is not None or pr
    if should_create_branch or commit:
        _ensure_clean_dependency_update_worktree()

    run_command(get_dependency_update_command(dependencies))
    if not _get_dependency_update_changed_files():
        LOGGER.info(
            "Dependency update completed with no lockfile or pyproject changes."
        )
        return

    if run_tests:
        test()

    changed_dependency_names = _get_changed_dependency_names() or sorted(dependencies)
    if should_create_branch:
        run_command(
            [
                "git",
                "checkout",
                "-b",
                branch_name or _dependency_update_branch_name(changed_dependency_names),
            ]
        )

    if commit or pr:
        run_command(
            [
                "git",
                "add",
                *[
                    path
                    for path in (
                        Path("pyproject.toml"),
                        Path("uv.lock"),
                    )
                    if path.exists()
                ],
            ]
        )
        run_command(
            ["git", "commit", "-m", _dependency_update_title(changed_dependency_names)]
        )

    if pr:
        current_branch = get_current_branch()
        run_command(["git", "push", "-u", "origin", current_branch])
        create_pull_request(
            title=_dependency_update_title(changed_dependency_names),
            head=current_branch,
            base=get_default_branch(),
            body="Automated dependency update.",
            draft=draft,
        )
