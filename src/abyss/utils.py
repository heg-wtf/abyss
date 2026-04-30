"""Utility functions for abyss."""

from __future__ import annotations

import html
import logging
import re
from datetime import datetime

from abyss.config import abyss_home

TELEGRAM_MESSAGE_LIMIT = 4096


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


def split_message(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Split a long message into chunks that fit Telegram's message limit.

    Tries to split at newline boundaries when possible.
    """
    if len(text) <= limit:
        return [text]

    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break

        split_index = text.rfind("\n", 0, limit)
        if split_index == -1 or split_index < limit // 2:
            split_index = limit

        chunks.append(text[:split_index])
        text = text[split_index:].lstrip("\n")

    return chunks


_SAFE_URL_SCHEMES = ("http", "https", "tg", "mailto")


def _sanitize_link_url(url: str) -> str | None:
    """Return URL if scheme is whitelisted, else None.

    Blocks javascript:, data:, vbscript:, file:, and schemeless URLs to prevent
    XSS through LLM-generated Markdown links. Defense-in-depth — Telegram clients
    typically strip dangerous schemes, but downstream renderers (dashboards,
    future channel adapters) must not see attack payloads in the canonical HTML.
    """
    stripped = url.strip()
    if ":" not in stripped:
        return None
    scheme = stripped.split(":", 1)[0].lower()
    if scheme not in _SAFE_URL_SCHEMES:
        return None
    return stripped


def markdown_to_telegram_html(text: str) -> str:
    """Convert Markdown formatting to Telegram-compatible HTML.

    Handles: **bold**, *italic*, `code`, ```code blocks```, [links](url)
    """
    # Extract links before escaping so URLs stay intact
    link_placeholder = {}
    link_counter = 0

    def _replace_link(match: re.Match) -> str:
        nonlocal link_counter
        placeholder = f"\x00LINK{link_counter}\x00"
        link_placeholder[placeholder] = (match.group(1), match.group(2))
        link_counter += 1
        return placeholder

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _replace_link, text)

    text = html.escape(text)

    text = re.sub(r"```(\w*)\n(.*?)```", r"<pre>\2</pre>", text, flags=re.DOTALL)
    text = re.sub(r"```(.*?)```", r"<pre>\1</pre>", text, flags=re.DOTALL)

    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    # Headings → bold
    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)

    # Restore links as HTML <a> tags. Drop the anchor for unsafe URLs.
    for placeholder, (link_text, url) in link_placeholder.items():
        escaped_text = html.escape(link_text)
        safe_url = _sanitize_link_url(url)
        if safe_url is None:
            text = text.replace(placeholder, escaped_text)
        else:
            escaped_url = html.escape(safe_url, quote=True)
            text = text.replace(placeholder, f'<a href="{escaped_url}">{escaped_text}</a>')

    return text


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
