import logging
import subprocess
from typing import ClassVar


class ColoredFormatter(logging.Formatter):
    """Format warning and error log levels with ANSI color codes."""

    COLORS: ClassVar = {
        "WARNING": "\033[93m",
        "ERROR": "\033[91m",
        "CRITICAL": "\033[91m",
        "RESET": "\033[0m",
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record with a colored level name.

        Args:
            record: The log record to format.

        Returns:
            The formatted log message.
        """
        log_color = self.COLORS.get(record.levelname, "")
        record.levelname = f"\033[1m{log_color}{record.levelname}{self.COLORS['RESET'] if log_color else ''}\033[0m"
        return super().format(record)


def configure_logger(logger: logging.Logger) -> None:
    """Configure a logger with the standard colored console formatter.

    Args:
        logger: Logger to configure.
    """
    while logger.handlers:
        logger.removeHandler(logger.handlers[0])

    handler = logging.StreamHandler()
    handler.setFormatter(ColoredFormatter("[%(asctime)s] %(levelname)s: %(message)s"))
    logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Create a standard logger for a repository maintenance script.

    Args:
        name: Logger name, usually the script's `__name__` value.

    Returns:
        A configured logger without parent propagation.
    """
    logger = logging.getLogger(name)
    logger.propagate = False
    logger.setLevel(logging.INFO)
    return logger


def log_dry_run(logger: logging.Logger, message: str, *args: object) -> None:
    """Log a dry-run informational message with a yellow prefix.

    Args:
        logger: Logger used to emit the message.
        message: Log message template.
        *args: Values interpolated into `message`.
    """
    logger.info("\033[93m[DRY RUN]\033[0m " + message, *args)


def commit_readme_update(commit_message: str) -> None:
    """Commit the current README changes.

    Args:
        commit_message: Message for the README update commit.
    """
    subprocess.run(["git", "add", "README.md"], check=True)
    subprocess.run(["git", "commit", "-m", commit_message], check=True)
