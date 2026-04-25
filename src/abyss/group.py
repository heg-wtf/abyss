"""Group management for multi-bot collaboration."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def _groups_directory() -> Path:
    """Return the groups directory path."""
    from abyss.config import abyss_home

    return abyss_home() / "groups"


def group_directory(name: str) -> Path:
    """Return the directory path for a specific group."""
    return _groups_directory() / name


def group_config_path(name: str) -> Path:
    """Return the path to a group's group.yaml."""
    return group_directory(name) / "group.yaml"


def load_group_config(name: str) -> dict[str, Any] | None:
    """Load a group's group.yaml. Returns None if it doesn't exist."""
    path = group_config_path(name)
    if not path.exists():
        return None
    with open(path) as file:
        return yaml.safe_load(file)


def save_group_config(name: str, config: dict[str, Any]) -> None:
    """Save a group's group.yaml."""
    directory = group_directory(name)
    directory.mkdir(parents=True, exist_ok=True)
    with open(group_config_path(name), "w") as file:
        yaml.dump(config, file, default_flow_style=False, allow_unicode=True)


def create_group(
    name: str,
    orchestrator: str,
    members: list[str],
) -> Path:
    """Create a new group with directory structure.

    Validates that orchestrator and all members are registered bots.
    Creates group.yaml, conversation/, and workspace/ directories.

    Returns the group directory path.

    Raises:
        ValueError: If group already exists, or bots are not registered.
    """
    from abyss.config import bot_exists

    if group_exists(name):
        raise ValueError(f"Group '{name}' already exists.")

    if not bot_exists(orchestrator):
        raise ValueError(f"Bot '{orchestrator}' is not registered.")

    for member in members:
        if not bot_exists(member):
            raise ValueError(f"Bot '{member}' is not registered.")

    directory = group_directory(name)
    directory.mkdir(parents=True, exist_ok=True)

    conversation_directory = directory / "conversation"
    conversation_directory.mkdir(exist_ok=True)

    workspace_directory = directory / "workspace"
    workspace_directory.mkdir(exist_ok=True)

    config: dict[str, Any] = {
        "name": name,
        "telegram_chat_id": None,
        "orchestrator": orchestrator,
        "members": members,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    save_group_config(name, config)

    return directory


def delete_group(name: str) -> None:
    """Delete a group and all its data.

    Raises:
        ValueError: If the group does not exist.
    """
    import shutil

    directory = group_directory(name)
    if not directory.exists():
        raise ValueError(f"Group '{name}' does not exist.")

    shutil.rmtree(directory)


def group_exists(name: str) -> bool:
    """Check if a group with this name exists."""
    return group_config_path(name).exists()


def list_groups() -> list[dict[str, Any]]:
    """List all groups with their configs.

    Returns a list of group config dicts. Empty list if no groups exist.
    """
    groups_dir = _groups_directory()
    if not groups_dir.exists():
        return []

    result: list[dict[str, Any]] = []
    for child in sorted(groups_dir.iterdir()):
        if child.is_dir():
            config = load_group_config(child.name)
            if config:
                result.append(config)
    return result


def find_group_by_chat_id(chat_id: int) -> dict[str, Any] | None:
    """Find a group config by its bound Telegram chat_id.

    Returns the group config dict, or None if no group is bound to this chat_id.
    """
    for group_config in list_groups():
        if group_config.get("telegram_chat_id") == chat_id:
            return group_config
    return None


def bind_group(name: str, chat_id: int) -> None:
    """Bind a Telegram chat_id to a group.

    Raises:
        ValueError: If the group does not exist.
    """
    config = load_group_config(name)
    if config is None:
        raise ValueError(f"Group '{name}' does not exist.")

    existing_group = find_group_by_chat_id(chat_id)
    if existing_group and existing_group["name"] != name:
        raise ValueError(f"Chat ID {chat_id} is already bound to group '{existing_group['name']}'.")

    config["telegram_chat_id"] = chat_id
    save_group_config(name, config)


def unbind_group(name: str) -> None:
    """Remove the Telegram chat_id binding from a group.

    Raises:
        ValueError: If the group does not exist.
    """
    config = load_group_config(name)
    if config is None:
        raise ValueError(f"Group '{name}' does not exist.")

    config["telegram_chat_id"] = None
    save_group_config(name, config)


def get_my_role(group_config: dict[str, Any], bot_name: str) -> str | None:
    """Determine a bot's role in a group.

    Returns "orchestrator", "member", or None if the bot is not in the group.
    """
    if group_config.get("orchestrator") == bot_name:
        return "orchestrator"
    if bot_name in group_config.get("members", []):
        return "member"
    return None


def find_groups_for_bot(bot_name: str) -> list[dict[str, Any]]:
    """Find all groups that a bot belongs to (as orchestrator or member).

    Returns a list of group config dicts.
    """
    result: list[dict[str, Any]] = []
    for group_config in list_groups():
        if get_my_role(group_config, bot_name) is not None:
            result.append(group_config)
    return result


# --- Shared Conversation Log ---

CONVERSATION_DATE_FORMAT = "%y%m%d"
CONVERSATION_TIMESTAMP_FORMAT = "%H:%M:%S"


def _shared_conversation_directory(group_name: str) -> Path:
    """Return the shared conversation directory for a group."""
    return group_directory(group_name) / "conversation"


def _shared_conversation_file_for_today(group_name: str) -> Path:
    """Return today's shared conversation file path."""
    date_string = datetime.now(timezone.utc).strftime(CONVERSATION_DATE_FORMAT)
    return _shared_conversation_directory(group_name) / f"{date_string}.md"


def log_to_shared_conversation(
    group_name: str,
    sender: str,
    content: str,
) -> None:
    """Append a message to the group's shared conversation log.

    Args:
        group_name: The group name.
        sender: Display name (e.g., "user" or "@bot_username").
        content: Message content.
    """
    conversation_file = _shared_conversation_file_for_today(group_name)
    conversation_file.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime(CONVERSATION_TIMESTAMP_FORMAT)
    entry = f"[{timestamp}] {sender}: {content}\n"

    with open(conversation_file, "a") as file:
        file.write(entry)

    _index_group_message(group_name, sender, content)


def _index_group_message(group_name: str, sender: str, content: str) -> None:
    """Mirror a shared-conversation message into the group's FTS5 index.

    Best-effort — markdown remains the source of truth, so any failure
    is logged and swallowed.
    """
    try:
        from abyss import conversation_index

        db_path = group_directory(group_name) / "conversation.db"
        conversation_index.append(
            db_path,
            chat_id="group",
            role=sender,
            content=content,
        )
    except Exception:
        import logging

        logging.getLogger(__name__).exception("failed to index group message in %s", group_name)


def load_shared_conversation(
    group_name: str,
    max_lines: int = 50,
) -> str:
    """Load recent shared conversation lines.

    Reads from newest to oldest conversation files until max_lines is reached.

    Returns the conversation text, or empty string if no conversation exists.
    """
    conversation_directory = _shared_conversation_directory(group_name)
    if not conversation_directory.exists():
        return ""

    conversation_files = sorted(
        conversation_directory.glob("[0-9][0-9][0-9][0-9][0-9][0-9].md"),
        reverse=True,
    )

    if not conversation_files:
        return ""

    all_lines: list[str] = []
    for conversation_file in conversation_files:
        content = conversation_file.read_text()
        if not content.strip():
            continue

        lines = [line for line in content.strip().split("\n") if line.strip()]
        all_lines = lines + all_lines

        if len(all_lines) >= max_lines:
            break

    if not all_lines:
        return ""

    recent_lines = all_lines[-max_lines:]
    return "\n".join(recent_lines)


def clear_shared_conversation(group_name: str) -> None:
    """Clear all shared conversation files for a group.

    Removes all .md files from the conversation directory.
    The directory itself is preserved.
    """
    conversation_directory = _shared_conversation_directory(group_name)
    if not conversation_directory.exists():
        return
    for file in conversation_directory.glob("*.md"):
        file.unlink()


# --- Shared Workspace ---


def shared_workspace_path(group_name: str) -> Path:
    """Return the shared workspace directory for a group."""
    workspace = group_directory(group_name) / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def list_workspace_files(group_name: str) -> list[str]:
    """List all files in the group's shared workspace.

    Returns a list of relative file paths within the workspace.
    """
    workspace = group_directory(group_name) / "workspace"
    if not workspace.exists():
        return []

    files: list[str] = []
    for file_path in sorted(workspace.rglob("*")):
        if file_path.is_file():
            files.append(str(file_path.relative_to(workspace)))
    return files
