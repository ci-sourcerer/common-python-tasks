import argparse
import sys

from .docs_tasks_reference import (
    DOCKERFILE_REFERENCE_FILE,
    TASK_CATEGORY_FILES,
    generate_task_reference_files,
    replace_dockerfile_reference,
    replace_task_reference,
)


def update_docs_references(check: bool = False) -> None:
    """Update or verify generated task and Dockerfile-reference documentation.

    Args:
        check: Verify files without modifying them.
    """
    outdated_files = []

    # Generate individual task reference files
    generate_task_reference_files()

    for category, path in TASK_CATEGORY_FILES.items():
        current_text = path.read_text(encoding="utf-8")
        updated_text = replace_task_reference(current_text, category)
        if updated_text == current_text:
            continue
        if check:
            outdated_files.append(path)
        else:
            path.write_text(updated_text, encoding="utf-8")

    current_text = DOCKERFILE_REFERENCE_FILE.read_text(encoding="utf-8")
    updated_text = replace_dockerfile_reference(current_text)
    if updated_text != current_text:
        if check:
            outdated_files.append(DOCKERFILE_REFERENCE_FILE)
        else:
            DOCKERFILE_REFERENCE_FILE.write_text(updated_text, encoding="utf-8")

    if outdated_files:
        sys.exit(
            "Generated documentation is outdated: "
            + ", ".join(str(path) for path in outdated_files)
        )


def main() -> None:
    """Parse arguments and update generated documentation."""
    parser = argparse.ArgumentParser(description="Update generated documentation")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if generated documentation is outdated.",
    )
    update_docs_references(check=parser.parse_args().check)


if __name__ == "__main__":
    main()
