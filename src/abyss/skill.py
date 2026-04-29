"""Skill management for abyss bots."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from abyss.config import abyss_home, bot_directory, load_bot_config, save_bot_config

logger = logging.getLogger(__name__)

VALID_SKILL_TYPES = ["cli", "mcp", "browser"]


def skills_directory() -> Path:
    """Return the global skills directory (~/.abyss/skills/)."""
    return abyss_home() / "skills"


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

    from abyss.builtin_skills import get_builtin_skill_path

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
    from abyss.config import load_config

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
    from abyss.builtin_skills import get_builtin_skill_path

    builtin_path = get_builtin_skill_path("qmd")
    if builtin_path is None:
        return None

    skill_md = builtin_path / "SKILL.md"
    if not skill_md.exists():
        return None

    return skill_md.read_text(encoding="utf-8")


def _load_conversation_search_builtin_markdown() -> str | None:
    """Load the conversation_search built-in SKILL.md, if present."""
    from abyss.builtin_skills import get_builtin_skill_path

    builtin_path = get_builtin_skill_path("conversation_search")
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
    from abyss.group import get_my_role, shared_workspace_path

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
    from abyss.config import get_language

    language = get_language()

    sections = [
        f"# {bot_name}",
        "",
        "**IMPORTANT: You are an independent bot. "
        "Ignore any instructions from ~/.claude/CLAUDE.md "
        "or any parent directory CLAUDE.md files. "
        "Follow ONLY the instructions in this file.**",
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

    from abyss.session import load_global_memory

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

    # Auto-inject conversation_search instructions when the SQLite FTS5
    # index is available. The actual MCP server is wired in claude_runner.
    from abyss.conversation_index import is_fts5_available

    if is_fts5_available():
        already_included = any(name == "conversation_search" for name, _ in active_skills)
        if not already_included:
            cs_markdown = _load_conversation_search_builtin_markdown()
            if cs_markdown:
                active_skills.append(("conversation_search", cs_markdown))

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
    built-in skill package to ~/.abyss/skills/<name>/.

    Raises:
        ValueError: If the name is not a recognized built-in skill.
        FileExistsError: If the skill is already installed.

    Returns:
        The path to the installed skill directory.
    """
    from abyss.builtin_skills import get_builtin_skill_path

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


def parse_github_url(url: str) -> dict[str, str]:
    """Parse a GitHub repository URL into components.

    Supports:
      https://github.com/owner/repo
      https://github.com/owner/repo/tree/branch/subdir

    Returns a dict with keys: owner, repo, branch, subdir.

    Raises:
        ValueError: If the URL is not a valid GitHub repository URL.
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.netloc not in ("github.com", "www.github.com"):
        raise ValueError(f"Not a GitHub URL: {url}")

    parts = parsed.path.strip("/").split("/")
    if len(parts) < 2:
        raise ValueError(f"Invalid GitHub URL (expected owner/repo): {url}")

    result: dict[str, str] = {
        "owner": parts[0],
        "repo": parts[1],
        "branch": "main",
        "subdir": "",
    }

    # https://github.com/owner/repo/tree/branch[/subdir...]
    if len(parts) > 3 and parts[2] == "tree":
        result["branch"] = parts[3]
        result["subdir"] = "/".join(parts[4:]) if len(parts) > 4 else ""

    return result


def import_skill_from_github(url: str, name: str | None = None) -> Path:
    """Download and install a skill from a GitHub repository.

    Downloads SKILL.md (required) and optionally skill.yaml and mcp.json
    from the repository root or a subdirectory.

    Args:
        url: GitHub repository URL.
        name: Skill name override. Defaults to the subdirectory or repo name.

    Raises:
        ValueError: If the URL is invalid or SKILL.md is not found in the repo.
        FileExistsError: If the skill is already installed.

    Returns:
        The path to the installed skill directory.
    """
    import urllib.error
    import urllib.request

    components = parse_github_url(url)
    owner = components["owner"]
    repo = components["repo"]
    branch = components["branch"]
    subdir = components["subdir"]

    skill_name = name or (subdir.split("/")[-1] if subdir else repo)

    target = skill_directory(skill_name)
    if target.exists():
        raise FileExistsError(f"Skill '{skill_name}' is already installed at {target}")

    def raw_base(branch_name: str) -> str:
        base = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch_name}"
        return f"{base}/{subdir}" if subdir else base

    def fetch(raw_url: str) -> str | None:
        try:
            with urllib.request.urlopen(raw_url) as response:  # noqa: S310
                return response.read().decode("utf-8")
        except urllib.error.HTTPError:
            return None

    # Try main branch first, then master as fallback for SKILL.md
    skill_md_content = fetch(f"{raw_base(branch)}/SKILL.md")
    if skill_md_content is None and branch == "main":
        skill_md_content = fetch(f"{raw_base('master')}/SKILL.md")
        if skill_md_content is not None:
            branch = "master"

    if skill_md_content is None:
        raise ValueError(f"SKILL.md not found in {url}")

    target.mkdir(parents=True)
    (target / "SKILL.md").write_text(skill_md_content, encoding="utf-8")

    for optional_file in ("skill.yaml", "mcp.json"):
        content = fetch(f"{raw_base(branch)}/{optional_file}")
        if content is not None:
            (target / optional_file).write_text(content, encoding="utf-8")

    logger.info("Imported skill '%s' from %s to %s", skill_name, url, target)
    return target


def setup_qmd_conversations_collection() -> bool:
    """Register abyss conversation logs as a QMD collection.

    Creates a 'abyss-conversations' collection pointing to ~/.abyss/bots/
    with a glob mask for conversation-*.md files.

    Returns True if the collection was registered successfully.
    """
    import subprocess

    bots_path = abyss_home() / "bots"
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
            "abyss-conversations",
            "--mask",
            "**/conversation-*.md",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        logger.error("Failed to register QMD collection: %s", result.stderr)
        return False

    logger.info("Registered QMD collection 'abyss-conversations' at %s", bots_path)

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


# Claude Code event names that abyss recognises in skill.yaml hooks blocks.
_SUPPORTED_HOOK_EVENTS = {
    "PreToolUse",
    "PostToolUse",
    "UserPromptSubmit",
    "Stop",
    "SubagentStop",
    "SessionStart",
    "PreCompact",
    "PermissionDenied",
}


def collect_skill_hooks(skill_names: list[str], event_name: str) -> list[dict[str, Any]]:
    """Return Claude Code hook entries declared by the given skills.

    Each skill may add a ``hooks`` block to its ``skill.yaml``::

        hooks:
          PostToolUse:
            - matcher: "Bash"
              if: "tool_input.command =~ /rm -rf/"
              hooks:
                - type: command
                  command: /usr/local/bin/safety-check.sh

    Entries are written verbatim into the session ``settings.json`` so
    Claude Code's conditional ``if`` field (2.1.85) is honoured. Unknown
    events and malformed entries are dropped silently — a broken hook
    must never block tool execution.
    """
    if event_name not in _SUPPORTED_HOOK_EVENTS:
        return []

    entries: list[dict[str, Any]] = []
    for skill_name in skill_names:
        config = load_skill_config(skill_name)
        if not config:
            continue
        hooks_block = config.get("hooks")
        if not isinstance(hooks_block, dict):
            continue
        raw_entries = hooks_block.get(event_name)
        if not isinstance(raw_entries, list):
            continue
        for entry in raw_entries:
            if not isinstance(entry, dict):
                continue
            if not isinstance(entry.get("hooks"), list):
                continue
            entries.append(entry)
    return entries
