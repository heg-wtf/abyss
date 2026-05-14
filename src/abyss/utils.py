"""Utility functions for abyss."""

from __future__ import annotations

import logging
from datetime import datetime

from abyss.config import abyss_home


def prompt_input(label: str, default: str | None = None) -> str:
    """Prompt for single-line input using builtin input() for IME compatibility."""
    from rich.console import Console

    if default is not None:
        Console().print(f"{label} [dim](default: {default})[/dim] ", end="")
        value = input().strip()
        return value if value else default
    else:
        Console().print(f"{label} ", end="")
        return input().strip()


def prompt_multiline(label: str) -> str:
    """Prompt for multi-line input. Empty line finishes input."""
    from rich.console import Console

    Console().print(f"{label} [dim](empty line to finish)[/dim]")
    lines = []
    while True:
        line = input()
        if line == "":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def setup_logging(log_level: str = "INFO") -> None:
    """Configure logging with daily rotation to ~/.abyss/logs/."""
    log_directory = abyss_home() / "logs"
    log_directory.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%y%m%d")
    log_file = log_directory / f"abyss-{today}.log"

    from rich.logging import RichHandler

    level = getattr(logging, log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            logging.FileHandler(log_file),
            RichHandler(
                level=level,
                rich_tracebacks=True,
                tracebacks_show_locals=False,
                show_path=False,
            ),
        ],
        force=True,
    )

    # Keep file handler with full format for log files
    file_handler = logging.root.handlers[0]
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    )
