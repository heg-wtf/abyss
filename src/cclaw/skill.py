"""Skill management for cclaw bots."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from cclaw.config import bot_directory, cclaw_home, load_bot_config, save_bot_config

logger = logging.getLogger(__name__)

VALID_SKILL_TYPES = ["cli", "mcp", "browser"]


def skills_directory() -> Path:
    """Return the global skills directory (~/.cclaw/skills/)."""
    return cclaw_home() / "skills"


def skill_directory(name: str) -> Path:
    """Return the directory for a specific skill."""
    return skills_directory() / name


def is_valid_skill_type(skill_type: str) -> bool:
    """Check if the skill type is valid."""
    return skill_type in VALID_SKILL_TYPES


# --- Recognition & Loading ---


def list_skills() -> list[dict[str, Any]]:
    """List all recognized skills (directories containing SKILL.md)."""
    directory = skills_directory()
    if not directory.exists():
        return []

    from cclaw.builtin_skills import get_builtin_skill_path

    result = []
    for entry in sorted(directory.iterdir()):
        if entry.is_dir() and (entry / "SKILL.md").exists():
            config = load_skill_config(entry.name)
            emoji = config.get("emoji", "") if config else ""

            # Fallback: read emoji from builtin template if not in installed config
            if not emoji:
                builtin_path = get_builtin_skill_path(entry.name)
                if builtin_path:
                    builtin_yaml_path = builtin_path / "skill.yaml"
                    if builtin_yaml_path.exists():
                        with open(builtin_yaml_path) as builtin_file:
                            builtin_config = yaml.safe_load(builtin_file) or {}
                        emoji = builtin_config.get("emoji", "")

            result.append(
                {
                    "name": entry.name,
                    "type": skill_type(entry.name),
                    "status": skill_status(entry.name),
                    "description": config.get("description", "") if config else "",
                    "emoji": emoji,
                }
            )
    return result


def is_skill(name: str) -> bool:
    """Check if a skill exists (SKILL.md present)."""
    return (skill_directory(name) / "SKILL.md").exists()


def load_skill_config(name: str) -> dict[str, Any] | None:
    """Load a skill's skill.yaml. Returns None if it doesn't exist."""
    path = skill_directory(name) / "skill.yaml"
    if not path.exists():
        return None
    with open(path) as file:
        return yaml.safe_load(file) or {}


def save_skill_config(name: str, config: dict[str, Any]) -> None:
    """Save a skill's skill.yaml."""
    path = skill_directory(name) / "skill.yaml"
    with open(path, "w") as file:
        yaml.dump(config, file, default_flow_style=False, allow_unicode=True)


def load_skill_markdown(name: str) -> str | None:
    """Load a skill's SKILL.md content. Returns None if it doesn't exist."""
    path = skill_directory(name) / "SKILL.md"
    if not path.exists():
        return None
    return path.read_text()


def skill_status(name: str) -> str:
    """Return the status of a skill: active, inactive, or not_found."""
    if not is_skill(name):
        return "not_found"

    config = load_skill_config(name)
    if config is None:
        # Markdown-only skill (no skill.yaml) is always active
        return "active"

    return config.get("status", "inactive")


def skill_type(name: str) -> str | None:
    """Return the skill type. None means markdown-only (no tools)."""
    config = load_skill_config(name)
    if config is None:
        return None
    return config.get("type")


# --- Creation & Deletion ---


def create_skill_directory(name: str) -> Path:
    """Create and return the skill directory."""
    directory = skill_directory(name)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def generate_skill_markdown(name: str, description: str = "") -> str:
    """Generate default SKILL.md content."""
    return f"""# {name}

{description}

## Instructions

(Describe what this skill does and how the bot should use it.)
"""


def default_skill_yaml(
    name: str,
    description: str = "",
    skill_type: str | None = None,
    required_commands: list[str] | None = None,
    environment_variables: list[str] | None = None,
) -> dict[str, Any]:
    """Return a default skill.yaml structure."""
    config: dict[str, Any] = {
        "name": name,
        "description": description,
        "status": "inactive",
    }
    if skill_type:
        config["type"] = skill_type
    if required_commands:
        config["required_commands"] = required_commands
    if environment_variables:
        config["environment_variables"] = environment_variables
    return config


def remove_skill(name: str) -> bool:
    """Remove a skill directory entirely.

    Also detaches it from all bots that use it.
    Returns True if the skill was found and removed.
    """
    directory = skill_directory(name)
    if not directory.exists():
        return False

    # Detach from all bots using this skill
    for bot_name in bots_using_skill(name):
        detach_skill_from_bot(bot_name, name)

    shutil.rmtree(directory)
    return True


# --- Setup & Activation ---


def check_skill_requirements(name: str) -> list[str]:
    """Check if skill requirements are met.

    Returns a list of error messages. Empty list means all OK.
    """
    errors: list[str] = []
    config = load_skill_config(name)
    if config is None:
        return errors  # Markdown-only, no requirements

    install_hints = config.get("install_hints", {})
    for command in config.get("required_commands", []):
        if not shutil.which(command):
            hint = install_hints.get(command)
            if hint:
                errors.append(f"Required command not found: {command}\n    Install: {hint}")
            else:
                errors.append(f"Required command not found: {command}")

    for variable in config.get("environment_variables", []):
        # Only check if the variable key is defined, value can be set during setup
        pass

    return errors


def activate_skill(name: str) -> None:
    """Set a skill's status to active."""
    config = load_skill_config(name)
    if config is None:
        return
    config["status"] = "active"
    save_skill_config(name, config)


# --- Bot-Skill Connection ---


def get_bot_skills(bot_name: str) -> list[str]:
    """Get the list of skill names attached to a bot."""
    bot_config = load_bot_config(bot_name)
    if not bot_config:
        return []
    return bot_config.get("skills", [])


def attach_skill_to_bot(bot_name: str, skill_name: str) -> None:
    """Attach a skill to a bot and regenerate CLAUDE.md."""
    bot_config = load_bot_config(bot_name)
    if not bot_config:
        return

    skills = bot_config.get("skills", [])
    if skill_name not in skills:
        skills.append(skill_name)
        bot_config["skills"] = skills
        save_bot_config(bot_name, bot_config)


def detach_skill_from_bot(bot_name: str, skill_name: str) -> None:
    """Detach a skill from a bot and regenerate CLAUDE.md."""
    bot_config = load_bot_config(bot_name)
    if not bot_config:
        return

    skills = bot_config.get("skills", [])
    if skill_name in skills:
        skills.remove(skill_name)
        bot_config["skills"] = skills
        save_bot_config(bot_name, bot_config)


def bots_using_skill(skill_name: str) -> list[str]:
    """Return a list of bot names that have this skill attached."""
    from cclaw.config import load_config

    config = load_config()
    if not config or not config.get("bots"):
        return []

    result = []
    for bot_entry in config["bots"]:
        bot_name = bot_entry["name"]
        bot_config = load_bot_config(bot_name)
        if bot_config and skill_name in bot_config.get("skills", []):
            result.append(bot_name)
    return result


# --- CLAUDE.md Composition ---


def _load_qmd_builtin_markdown() -> str | None:
    """Load QMD SKILL.md from the builtin skills directory."""
    from cclaw.builtin_skills import get_builtin_skill_path

    builtin_path = get_builtin_skill_path("qmd")
    if builtin_path is None:
        return None

    skill_md = builtin_path / "SKILL.md"
    if not skill_md.exists():
        return None

    return skill_md.read_text(encoding="utf-8")


def compose_group_context(bot_name: str, group_config: dict[str, Any]) -> str:
    """Generate group context section for CLAUDE.md.

    Produces different content depending on whether the bot is the orchestrator
    or a member of the group.

    Args:
        bot_name: The bot's registered name.
        group_config: The group's config dict (from group.yaml).

    Returns:
        Markdown string to append to CLAUDE.md.
    """
    from cclaw.group import get_my_role, shared_workspace_path

    my_role = get_my_role(group_config, bot_name)
    group_name = group_config["name"]

    if my_role == "orchestrator":
        lines = [
            f"# Group: {group_name}",
            "",
            "You are the orchestrator of this group.",
            "",
            "## Team Members",
        ]
        for member_name in group_config.get("members", []):
            member_config = load_bot_config(member_name)
            if not member_config:
                continue
            username = member_config.get("telegram_username", "")
            member_personality = member_config.get("personality", "")
            member_role = member_config.get("role", "")
            member_goal = member_config.get("goal", "")
            lines.append(f"### {username}")
            lines.append(f"- personality: {member_personality}")
            lines.append(f"- role: {member_role}")
            lines.append(f"- goal: {member_goal}")
            lines.append("")

        workspace = shared_workspace_path(group_name)
        lines.extend(
            [
                "## Rules",
                "1. If the mission is ambiguous, ask clarifying questions "
                "BEFORE breaking it into tasks",
                "2. Analyze the mission and break it into tasks",
                "3. Delegate tasks to members via @mention",
                "4. Reallocate on failure or direction change",
                "5. Synthesize results and report to the user",
                "",
                "## Shared Workspace",
                f"Results go to: {workspace}",
            ]
        )
        return "\n".join(lines)

    if my_role == "member":
        orchestrator_name = group_config.get("orchestrator", "")
        orchestrator_config = load_bot_config(orchestrator_name)
        orchestrator_username = ""
        if orchestrator_config:
            orchestrator_username = orchestrator_config.get("telegram_username", "")

        workspace = shared_workspace_path(group_name)
        return "\n".join(
            [
                f"# Group: {group_name}",
                "",
                "You are a member of this group.",
                "",
                "## Rules",
                "- Only respond when @mentioned",
                f"- Report results to {orchestrator_username}",
                f"- Save work to: {workspace}",
            ]
        )

    return ""


def compose_claude_md(
    bot_name: str,
    personality: str,
    role: str,
    goal: str = "",
    skill_names: list[str] | None = None,
    bot_path: Path | None = None,
    group_context: dict[str, Any] | None = None,
) -> str:
    """Compose a full CLAUDE.md combining bot profile and skill content.

    When skill_names is empty or None, output is identical to generate_claude_md().
    When bot_path is provided, a Memory section is appended with instructions
    for the bot to save and retrieve long-term memories.
    When group_context is provided (a group config dict), a group context section
    is appended with orchestrator/member role instructions.
    """
    from cclaw.config import get_language

    language = get_language()

    sections = [
        f"# {bot_name}",
        "",
        "## Personality",
        personality,
        "",
        "## Role",
        role,
    ]

    if goal:
        sections.extend(["", "## Goal", goal])

    sections.extend(
        [
            "",
            "## Rules",
            f"- Respond in {language}.",
            "- Save generated files to the workspace/ directory.",
            "- Always ask for confirmation before executing dangerous commands "
            "(delete, restart, etc.).",
            "- **절대로 Markdown 표(table)를 사용하지 마라.** "
            "Telegram에서 표는 깨진다. "
            "대신 이모지 + 한 줄씩 나열하라. "
            "예시:\n"
            "  🌡 최저 -2°C / 최고 7°C\n"
            "  🌧 오전 한때 비 (5mm 미만)\n"
            "  ☁️ 오후~밤 차차 맑아짐",
        ]
    )

    from cclaw.session import load_global_memory

    global_memory = load_global_memory()
    if global_memory:
        sections.append("")
        sections.append("## Global Memory (Read-Only)")
        sections.append("- 아래는 모든 봇이 공유하는 글로벌 메모리이다. 참고만 하고 수정하지 마라.")
        sections.append("")
        sections.append(global_memory.strip())

    if bot_path is not None:
        memory_path = bot_path / "MEMORY.md"
        sections.append("")
        sections.append("## Memory")
        sections.append(
            "- 사용자가 무언가를 기억하라고 요청하면(언어 무관), MEMORY.md 파일에 추가하라."
        )
        sections.append(f"- MEMORY.md 경로: {memory_path}")
        sections.append("- 기존 내용을 유지하고, 새 항목을 추가하라.")
        sections.append("- 카테고리별로 정리하라 (개인정보, 선호사항, 프로젝트, 기타).")

    # Collect skills (attached + auto-injected)
    active_skills = []

    if skill_names:
        for skill_name in skill_names:
            markdown = load_skill_markdown(skill_name)
            if markdown is not None:
                active_skills.append((skill_name, markdown))

    # Auto-inject QMD instructions if CLI is available (system-wide, all bots)
    if shutil.which("qmd"):
        # Check if qmd is already in the skill list (avoid duplicate)
        qmd_already_included = any(name == "qmd" for name, _ in active_skills)
        if not qmd_already_included:
            qmd_markdown = _load_qmd_builtin_markdown()
            if qmd_markdown:
                active_skills.append(("qmd", qmd_markdown))

    if active_skills:
        sections.append("")
        sections.append("---")
        sections.append("")
        sections.append("# Available Skills")
        for skill_name, markdown in active_skills:
            sections.append("")
            sections.append(f"## {skill_name}")
            sections.append("")
            sections.append(markdown.strip())

    if group_context is not None:
        group_section = compose_group_context(bot_name, group_context)
        if group_section:
            sections.append("")
            sections.append("---")
            sections.append("")
            sections.append(group_section)

    sections.append("")
    return "\n".join(sections)


def regenerate_bot_claude_md(bot_name: str) -> None:
    """Regenerate a bot's CLAUDE.md based on current bot.yaml (including skills)."""
    bot_config = load_bot_config(bot_name)
    if not bot_config:
        return

    directory = bot_directory(bot_name)
    content = compose_claude_md(
        bot_name=bot_name,
        personality=bot_config.get("personality", ""),
        role=bot_config.get("role", bot_config.get("description", "")),
        goal=bot_config.get("goal", ""),
        skill_names=bot_config.get("skills", []),
        bot_path=directory,
    )
    claude_md_path = directory / "CLAUDE.md"
    claude_md_path.write_text(content)


def update_session_claude_md(bot_path: Path) -> None:
    """Propagate the bot's CLAUDE.md to all existing sessions."""
    bot_claude_md = bot_path / "CLAUDE.md"
    if not bot_claude_md.exists():
        return

    content = bot_claude_md.read_text()
    sessions_directory = bot_path / "sessions"
    if not sessions_directory.exists():
        return

    for session in sessions_directory.iterdir():
        if session.is_dir():
            session_claude_md = session / "CLAUDE.md"
            session_claude_md.write_text(content)


# --- MCP / Environment Variables ---


def load_skill_mcp_config(name: str) -> dict[str, Any] | None:
    """Load MCP configuration from a skill's mcp.json."""
    path = skill_directory(name) / "mcp.json"
    if not path.exists():
        return None
    with open(path) as file:
        return json.load(file)


def merge_mcp_configs(skill_names: list[str]) -> dict[str, Any] | None:
    """Merge MCP configurations from multiple skills.

    Returns a combined mcpServers dict, or None if no skills have MCP config.
    """
    merged_servers: dict[str, Any] = {}

    for skill_name in skill_names:
        mcp_config = load_skill_mcp_config(skill_name)
        if mcp_config and "mcpServers" in mcp_config:
            merged_servers.update(mcp_config["mcpServers"])

    if not merged_servers:
        return None

    return {"mcpServers": merged_servers}


def install_builtin_skill(name: str) -> Path:
    """Install a built-in skill template to the user's skills directory.

    Copies all template files (SKILL.md, skill.yaml, etc.) from the
    built-in skill package to ~/.cclaw/skills/<name>/.

    Raises:
        ValueError: If the name is not a recognized built-in skill.
        FileExistsError: If the skill is already installed.

    Returns:
        The path to the installed skill directory.
    """
    from cclaw.builtin_skills import get_builtin_skill_path

    template_path = get_builtin_skill_path(name)
    if template_path is None:
        raise ValueError(f"Unknown built-in skill: {name}")

    target = skill_directory(name)
    if target.exists():
        raise FileExistsError(f"Skill '{name}' is already installed at {target}")

    target.mkdir(parents=True)
    for source_file in template_path.iterdir():
        if source_file.is_file():
            shutil.copy2(source_file, target / source_file.name)

    logger.info("Installed built-in skill '%s' to %s", name, target)
    return target


def setup_qmd_conversations_collection() -> bool:
    """Register cclaw conversation logs as a QMD collection.

    Creates a 'cclaw-conversations' collection pointing to ~/.cclaw/bots/
    with a glob mask for conversation-*.md files.

    Returns True if the collection was registered successfully.
    """
    import subprocess

    bots_path = cclaw_home() / "bots"
    if not bots_path.exists():
        logger.warning("No bots directory found, skipping QMD collection setup")
        return False

    result = subprocess.run(
        [
            "qmd",
            "collection",
            "add",
            str(bots_path),
            "--name",
            "cclaw-conversations",
            "--mask",
            "**/conversation-*.md",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        logger.error("Failed to register QMD collection: %s", result.stderr)
        return False

    logger.info("Registered QMD collection 'cclaw-conversations' at %s", bots_path)

    # Run indexing
    subprocess.run(["qmd", "update"], capture_output=True, text=True)
    logger.info("QMD index updated")

    return True


def collect_skill_allowed_tools(skill_names: list[str]) -> list[str]:
    """Collect allowed_tools from all specified skills.

    Returns a merged list of tool patterns for --allowedTools flag.
    """
    result: list[str] = []

    for skill_name in skill_names:
        config = load_skill_config(skill_name)
        if not config:
            continue

        tools = config.get("allowed_tools", [])
        if tools:
            result.extend(tools)

    return result


def collect_skill_environment_variables(skill_names: list[str]) -> dict[str, str]:
    """Collect environment variables from all specified skills.

    Returns a merged dict of environment variable name → value.
    """
    result: dict[str, str] = {}

    for skill_name in skill_names:
        config = load_skill_config(skill_name)
        if not config:
            continue

        env_values = config.get("environment_variable_values", {})
        if env_values:
            result.update(env_values)

    return result
