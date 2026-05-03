"""Session directory management for abyss."""

from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

CLAUDE_SESSION_ID_FILE = ".claude_session_id"
MEMORY_FILE_NAME = "MEMORY.md"
GLOBAL_MEMORY_FILE_NAME = "GLOBAL_MEMORY.md"
MAX_CONVERSATION_HISTORY_TURNS = 20
CONVERSATION_FILE_PREFIX = "conversation-"
CONVERSATION_FILE_SUFFIX = ".md"
CONVERSATION_DATE_FORMAT = "%y%m%d"
CONVERSATION_GLOB_PATTERN = "conversation-[0-9][0-9][0-9][0-9][0-9][0-9].md"


def session_directory(bot_path: Path, chat_id: int | str) -> Path:
    """Return the session directory path for a given chat.

    For integer chat_id (Telegram), directory is ``chat_<int>``.
    For string chat_id (e.g. dashboard ``chat_web_<uuid>``), the string is
    used verbatim as the directory name — callers must include any prefix
    they want.
    """
    if isinstance(chat_id, int):
        return bot_path / "sessions" / f"chat_{chat_id}"
    return bot_path / "sessions" / chat_id


WEB_SESSION_PREFIX = "chat_web_"


def collect_web_session_ids(bot_path: Path) -> list[str]:
    """Collect dashboard chat session IDs (``chat_web_<uuid>``) for a bot.

    Returns directory names verbatim (e.g. ``chat_web_a3f9b2c1``).
    """
    sessions_directory = bot_path / "sessions"
    if not sessions_directory.exists():
        return []
    out: list[str] = []
    for child in sorted(sessions_directory.iterdir()):
        if child.is_dir() and child.name.startswith(WEB_SESSION_PREFIX):
            out.append(child.name)
    return out


def collect_session_chat_ids(bot_path: Path) -> list[int]:
    """Collect chat IDs from existing session directories.

    Scans ``sessions/chat_<id>/`` directories and returns the list of chat IDs.
    Used as a fallback when ``allowed_users`` is empty but the bot needs to
    send proactive messages (cron results, heartbeat notifications).
    """
    sessions_directory = bot_path / "sessions"
    if not sessions_directory.exists():
        return []
    chat_ids: list[int] = []
    for child in sorted(sessions_directory.iterdir()):
        if child.is_dir() and child.name.startswith("chat_"):
            try:
                chat_id = int(child.name.removeprefix("chat_"))
                chat_ids.append(chat_id)
            except ValueError:
                continue
    return chat_ids


def ensure_session(
    bot_path: Path,
    chat_id: int | str,
    *,
    bot_name: str | None = None,
) -> Path:
    """Ensure a session directory exists with required files.

    Creates the session directory, copies the bot's CLAUDE.md into it,
    and creates the workspace subdirectory.

    When bot_name is provided, checks if the chat_id belongs to a bound group
    and regenerates the session CLAUDE.md with group context if so.

    Returns the session directory path.
    """
    directory = session_directory(bot_path, chat_id)
    directory.mkdir(parents=True, exist_ok=True)

    workspace = directory / "workspace"
    workspace.mkdir(exist_ok=True)

    session_claude_md = directory / "CLAUDE.md"
    bot_claude_md = bot_path / "CLAUDE.md"

    if bot_name is not None and isinstance(chat_id, int):
        # Group binding only applies to integer Telegram chat IDs.
        from abyss.group import find_group_by_chat_id

        group_config = find_group_by_chat_id(chat_id)
        if group_config is not None:
            # Generate group-aware CLAUDE.md for this session
            from abyss.config import load_bot_config
            from abyss.skill import compose_claude_md

            bot_config = load_bot_config(bot_name)
            if bot_config:
                content = compose_claude_md(
                    bot_name=bot_name,
                    personality=bot_config.get("personality", ""),
                    role=bot_config.get("role", bot_config.get("description", "")),
                    goal=bot_config.get("goal", ""),
                    skill_names=bot_config.get("skills", []),
                    bot_path=bot_path,
                    group_context=group_config,
                )
                session_claude_md.write_text(content)
                return directory

    if not session_claude_md.exists() and bot_claude_md.exists():
        shutil.copy2(bot_claude_md, session_claude_md)

    return directory


def _conversation_file_for_today(session_directory: Path) -> Path:
    """Return today's conversation file path (conversation-YYMMDD.md)."""
    date_string = datetime.now(timezone.utc).strftime(CONVERSATION_DATE_FORMAT)
    return session_directory / f"{CONVERSATION_FILE_PREFIX}{date_string}{CONVERSATION_FILE_SUFFIX}"


def _list_all_conversation_files(session_directory: Path) -> list[Path]:
    """List all conversation files (dated + legacy) in the session directory."""
    if not session_directory.exists():
        return []
    files = list(session_directory.glob(CONVERSATION_GLOB_PATTERN))
    legacy_file = session_directory / "conversation.md"
    if legacy_file.exists():
        files.append(legacy_file)
    return files


def conversation_status_summary(session_directory: Path) -> str:
    """Return a human-readable summary of conversation files in the session."""
    if not session_directory.exists():
        return "No conversation yet"

    conversation_files = list(session_directory.glob(CONVERSATION_GLOB_PATTERN))
    legacy_file = session_directory / "conversation.md"

    total_size = 0
    file_count = 0

    for file in conversation_files:
        total_size += file.stat().st_size
        file_count += 1

    if legacy_file.exists():
        total_size += legacy_file.stat().st_size
        file_count += 1

    if file_count == 0:
        return "No conversation yet"

    return f"{total_size:,} bytes ({file_count} files)"


def reset_session(bot_path: Path, chat_id: int) -> None:
    """Reset a session by deleting all conversation files (keep workspace)."""
    directory = session_directory(bot_path, chat_id)
    for conversation_file in _list_all_conversation_files(directory):
        conversation_file.unlink()
    clear_claude_session_id(directory)


def reset_all_session(bot_path: Path, chat_id: int) -> None:
    """Reset a session completely by deleting the entire session directory."""
    directory = session_directory(bot_path, chat_id)
    if directory.exists():
        shutil.rmtree(directory)


def get_claude_session_id(session_directory: Path) -> str | None:
    """Read stored Claude Code session ID."""
    path = session_directory / CLAUDE_SESSION_ID_FILE
    if path.exists():
        return path.read_text().strip()
    return None


def save_claude_session_id(session_directory: Path, session_id: str) -> None:
    """Store Claude Code session ID."""
    (session_directory / CLAUDE_SESSION_ID_FILE).write_text(session_id)


def clear_claude_session_id(session_directory: Path) -> None:
    """Remove stored Claude Code session ID."""
    (session_directory / CLAUDE_SESSION_ID_FILE).unlink(missing_ok=True)


def load_conversation_history(
    session_directory: Path, max_turns: int = MAX_CONVERSATION_HISTORY_TURNS
) -> str | None:
    """Read last N turns from conversation files.

    Searches conversation-YYMMDD.md files from newest to oldest,
    collecting turns until max_turns is reached.
    Falls back to legacy conversation.md if no dated files exist.

    Returns None if no conversation files exist or all are empty.
    """
    # Dated files in reverse chronological order (newest first)
    conversation_files = sorted(
        session_directory.glob(CONVERSATION_GLOB_PATTERN),
        reverse=True,
    )

    # Legacy fallback
    if not conversation_files:
        legacy_file = session_directory / "conversation.md"
        if legacy_file.exists():
            conversation_files = [legacy_file]

    if not conversation_files:
        return None

    all_sections: list[str] = []

    for conversation_file in conversation_files:
        content = conversation_file.read_text()
        if not content.strip():
            continue

        sections = re.split(r"(?=\n## (?:user|assistant) \()", content)
        sections = [s.strip() for s in sections if s.strip()]

        # Prepend older file's sections before newer ones
        all_sections = sections + all_sections

        if len(all_sections) >= max_turns:
            break

    if not all_sections:
        return None

    recent_sections = all_sections[-max_turns:]
    return "\n\n".join(recent_sections)


def log_conversation(session_directory: Path, role: str, content: str) -> None:
    """Append a conversation entry to today's conversation file.

    Writes to conversation-YYMMDD.md (UTC date).

    Args:
        session_directory: Path to the session directory.
        role: Either 'user' or 'assistant'.
        content: The message content.
    """
    conversation_file = _conversation_file_for_today(session_directory)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    entry = f"\n## {role} ({timestamp})\n\n{content}\n"

    with open(conversation_file, "a") as file:
        file.write(entry)

    _index_session_message(session_directory, role, content)


def _index_session_message(session_directory: Path, role: str, content: str) -> None:
    """Mirror a logged message into the bot's FTS5 conversation index.

    Best-effort: markdown remains the source of truth, so any failure
    here (sqlite, import, unexpected bug) is swallowed.
    """
    try:
        bot_dir = session_directory.parents[1]
    except IndexError:
        return

    chat_id = session_directory.name

    try:
        from abyss import conversation_index

        db_path = bot_dir / "conversation.db"
        conversation_index.append(
            db_path,
            chat_id=chat_id,
            role=role,
            content=content,
        )
    except Exception:
        import logging

        logging.getLogger(__name__).exception("failed to index session message in %s", bot_dir)


def list_workspace_files(session_directory: Path) -> list[str]:
    """List all files in the session's workspace directory.

    Returns a list of relative file paths within the workspace.
    """
    workspace = session_directory / "workspace"
    if not workspace.exists():
        return []

    files = []
    for file_path in sorted(workspace.rglob("*")):
        if file_path.is_file():
            files.append(str(file_path.relative_to(workspace)))
    return files


# --- Bot-level memory ---


def memory_file_path(bot_path: Path) -> Path:
    """Return the path to the bot's MEMORY.md file."""
    return bot_path / MEMORY_FILE_NAME


def load_bot_memory(bot_path: Path) -> str | None:
    """Load the bot's MEMORY.md content.

    Returns None if MEMORY.md doesn't exist or is empty.
    """
    path = memory_file_path(bot_path)
    if not path.exists():
        return None
    content = path.read_text()
    if not content.strip():
        return None
    return content


def save_bot_memory(bot_path: Path, content: str) -> None:
    """Save content to the bot's MEMORY.md file."""
    memory_file_path(bot_path).write_text(content)


def clear_bot_memory(bot_path: Path) -> None:
    """Delete the bot's MEMORY.md file."""
    memory_file_path(bot_path).unlink(missing_ok=True)


# --- Global memory ---


def global_memory_file_path() -> Path:
    """Return the path to the global GLOBAL_MEMORY.md file."""
    from abyss.config import abyss_home

    return abyss_home() / GLOBAL_MEMORY_FILE_NAME


def load_global_memory() -> str | None:
    """Load the global GLOBAL_MEMORY.md content.

    Returns None if GLOBAL_MEMORY.md doesn't exist or is empty.
    """
    path = global_memory_file_path()
    if not path.exists():
        return None
    content = path.read_text()
    if not content.strip():
        return None
    return content


def save_global_memory(content: str) -> None:
    """Save content to the global GLOBAL_MEMORY.md file."""
    from abyss.config import ensure_home

    ensure_home()
    global_memory_file_path().write_text(content)


def clear_global_memory() -> None:
    """Delete the global GLOBAL_MEMORY.md file."""
    global_memory_file_path().unlink(missing_ok=True)
