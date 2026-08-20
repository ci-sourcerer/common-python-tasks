import os
import sys
from pathlib import Path

from .readme_tasks_table import replace_tasks_table
from .utils import commit_readme_update, configure_logger, get_logger, log_dry_run

LOGGER = get_logger(__name__)


def main() -> None:
    """Update the README task table from the current task definitions."""
    configure_logger(LOGGER)

    readme_path = Path("README.md")
    readme_text = readme_path.read_text(encoding="utf-8")

    if os.environ.get("RELEASE_SCRIPT_DRY_RUN") == "1":
        updated_text = replace_tasks_table(readme_text)
        if updated_text == readme_text:
            log_dry_run(LOGGER, "README.md task table is already up to date")
        else:
            log_dry_run(LOGGER, "Would update README.md task table")
        return

    updated_text = replace_tasks_table(readme_text)
    if updated_text == readme_text:
        sys.exit("README.md task table was not changed")

    readme_path.write_text(updated_text, encoding="utf-8")
    commit_readme_update("chore(docs): refresh README task table")


if __name__ == "__main__":
    main()
