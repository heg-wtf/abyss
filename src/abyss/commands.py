"""Platform-independent slash command implementations.

Each ``cmd_*`` function performs a single slash command and returns a
``CommandResult``. Adapters (Telegram handlers, dashboard chat server)
translate between their platform's request/response types and these
pure functions.

The functions never reference ``telegram.Update`` or aiohttp request
objects. They only depend on ``CommandContext`` and abyss internals
(``session``, ``config``, ``group``...).

Phase 1 covers the commands that do not require Claude invocations or
multi-message conversational state. Streaming-heavy or stateful
commands (cron add, skills attach, compact, bind/unbind multi-step
flows) are extracted in subsequent phases.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from abyss.config import (
    DEFAULT_MODEL,
    DEFAULT_STREAMING,
    VALID_MODELS,
    is_valid_model,
    model_display_name,
    save_bot_config,
)
from abyss.group import (
    bind_group,
    clear_shared_conversation,
    find_group_by_chat_id,
    get_my_role,
    load_group_config,
    unbind_group,
)
from abyss.session import (
    clear_bot_memory,
    conversation_status_summary,
    ensure_session,
    list_workspace_files,
    load_bot_memory,
    reset_all_session,
    reset_session,
)

logger = logging.getLogger(__name__)


ParseMode = str  # "Markdown" | "HTML" | "None"


@dataclass
class CommandResult:
    """Outcome of running a slash command.

    Adapters convert this to a platform-specific reply (Telegram
    message, dashboard SSE event, etc.).
    """

    text: str = ""
    parse_mode: ParseMode | None = "Markdown"
    file_path: Path | None = None  # Set by /send so the adapter uploads it.
    success: bool = True
    silent: bool = False  # True means "do not send any reply" (e.g. group non-orchestrator skip).


@dataclass
class CommandContext:
    """Inputs for a slash command.

    ``chat_id`` is the per-conversation key. Telegram passes the
    Telegram chat id (``int``); the dashboard passes its session id
    (``str``). The downstream ``session_directory`` helper accepts
    both, and group lookups via ``find_group_by_chat_id`` only resolve
    integer Telegram chat ids — for dashboard sessions the lookup
    returns ``None`` and the command treats the chat as a DM. This
    matches existing dashboard behaviour where group features are
    Telegram-only.
    """

    bot_name: str
    bot_path: Path
    bot_config: dict[str, Any]
    chat_id: int | str
    args: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Simple, read-only or trivially mutating commands
# ---------------------------------------------------------------------------


async def cmd_start(ctx: CommandContext) -> CommandResult:
    """Introduce the bot using its configured persona."""

    display_name = ctx.bot_config.get("display_name") or ctx.bot_name
    personality = ctx.bot_config.get("personality", "")
    role = ctx.bot_config.get("role", ctx.bot_config.get("description", ""))
    goal = ctx.bot_config.get("goal", "")

    lines = [
        f"\U0001f916 *{display_name}*",
        "",
        f"\U0001f3ad *Personality:* {personality}",
        f"\U0001f4bc *Role:* {role}",
    ]
    if goal:
        lines.append(f"\U0001f3af *Goal:* {goal}")
    lines.extend(
        [
            "",
            "\U0001f4ac Send me a message to start chatting!",
            "\U00002753 Type /help for available commands.",
        ]
    )
    return CommandResult(text="\n".join(lines))


async def cmd_help(ctx: CommandContext) -> CommandResult:
    """List available slash commands."""

    text = (
        "\U0001f4cb *Available Commands:*\n\n"
        "\U0001f44b /start - Bot introduction\n"
        "\U0001f504 /reset - Clear conversation (keep workspace)\n"
        "\U0001f5d1 /resetall - Delete entire session\n"
        "\U0001f4c2 /files - List workspace files\n"
        "\U0001f4e4 /send - Send workspace file\n"
        "\U0001f4ca /status - Session status\n"
        "\U0001f9e0 /model - Show or change model\n"
        "\U0001f4e1 /streaming - Toggle streaming mode\n"
        "\U0001f9e0 /memory - Show or clear memory\n"
        "\U0001f9e9 /skills - Skill management\n"
        "⏰ /cron - Cron job management\n"
        "\U0001f493 /heartbeat - Heartbeat management\n"
        "\U0001f4e6 /compact - Compact MD files\n"
        "⛔ /cancel - Stop running process\n"
        "\U00002139 /version - Show version\n"
        "\U00002753 /help - Show this message"
    )
    return CommandResult(text=text)


async def cmd_version(ctx: CommandContext) -> CommandResult:
    """Print the installed abyss version."""

    from abyss import __version__

    return CommandResult(text=f"\U00002139 abyss v{__version__}", parse_mode=None)


async def cmd_status(ctx: CommandContext) -> CommandResult:
    """Summarise the current session: conversation status + workspace file count."""

    session_directory = ensure_session(ctx.bot_path, ctx.chat_id)
    conversation = conversation_status_summary(session_directory)
    files = list_workspace_files(session_directory)

    text = (
        f"\U0001f4ca *Session Status*\n\n"
        f"\U0001f916 Bot: {ctx.bot_name}\n"
        f"\U0001f4ac Chat ID: {ctx.chat_id}\n"
        f"\U0001f4dd Conversation: {conversation}\n"
        f"\U0001f4c2 Workspace files: {len(files)}"
    )
    return CommandResult(text=text)


async def cmd_files(ctx: CommandContext) -> CommandResult:
    """List the workspace files for this session."""

    session_directory = ensure_session(ctx.bot_path, ctx.chat_id)
    files = list_workspace_files(session_directory)

    if not files:
        return CommandResult(text="\U0001f4c2 No files in workspace.", parse_mode=None)

    file_list = "\n".join(f"  {name}" for name in files)
    return CommandResult(text=f"\U0001f4c2 *Workspace files:*\n```\n{file_list}\n```")


async def cmd_memory(ctx: CommandContext) -> CommandResult:
    """Show or clear the bot's persisted memory (MEMORY.md)."""

    if not ctx.args:
        memory_content = load_bot_memory(ctx.bot_path)
        if not memory_content:
            return CommandResult(text="\U0001f9e0 No memories saved yet.", parse_mode=None)
        # Adapter is responsible for HTML conversion + chunking when needed.
        # ``parse_mode="HTML"`` mirrors the original Telegram path so the
        # adapter can call ``markdown_to_telegram_html`` + ``split_message``
        # before sending.
        return CommandResult(text=memory_content, parse_mode="HTML")

    subcommand = ctx.args[0].lower()
    if subcommand == "clear":
        clear_bot_memory(ctx.bot_path)
        return CommandResult(text="\U0001f9e0 Memory cleared.", parse_mode=None)

    return CommandResult(
        text="Usage: `/memory` (show) or `/memory clear`",
        success=False,
    )


async def cmd_resetall(ctx: CommandContext) -> CommandResult:
    """Delete the entire session directory.

    The adapter must close the SDK pool session for the same
    ``bot_name:chat_id`` key after this returns, since pool lifecycle
    is platform-specific (Telegram and dashboard may keep different
    handles).
    """

    reset_all_session(ctx.bot_path, ctx.chat_id)
    return CommandResult(text="\U0001f5d1 Session completely reset.", parse_mode=None)


@dataclass
class ResetOutcome:
    """Detailed outcome of ``cmd_reset`` so adapters can drive pool/SDK cleanup."""

    result: CommandResult
    is_group: bool = False
    is_orchestrator: bool = False
    affected_bots: list[str] = field(default_factory=list)


async def cmd_reset(ctx: CommandContext) -> ResetOutcome:
    """Reset this bot's conversation. Group-aware.

    Returns a ``ResetOutcome`` so the adapter can close SDK pool
    sessions for every affected bot. The text reply for the user is
    inside ``outcome.result``.
    """

    group_config = find_group_by_chat_id(ctx.chat_id) if isinstance(ctx.chat_id, int) else None

    if group_config is not None:
        my_role = get_my_role(group_config, ctx.bot_name)
        if my_role != "orchestrator":
            # Only the orchestrator handles group /reset.
            return ResetOutcome(
                result=CommandResult(silent=True),
                is_group=True,
                is_orchestrator=False,
            )

        from abyss.config import bot_directory as get_bot_directory

        affected: list[str] = [ctx.bot_name]
        reset_session(ctx.bot_path, ctx.chat_id)

        for member_name in group_config.get("members", []):
            member_path = get_bot_directory(member_name)
            reset_session(member_path, ctx.chat_id)
            affected.append(member_name)

        clear_shared_conversation(group_config["name"])

        message = (
            "\U0001f504 Group session reset. Shared conversation cleared. Workspace preserved."
        )
        return ResetOutcome(
            result=CommandResult(text=message, parse_mode=None),
            is_group=True,
            is_orchestrator=True,
            affected_bots=affected,
        )

    reset_session(ctx.bot_path, ctx.chat_id)
    return ResetOutcome(
        result=CommandResult(
            text="\U0001f504 Conversation reset. Workspace files preserved.",
            parse_mode=None,
        ),
        affected_bots=[ctx.bot_name],
    )


async def cmd_model(ctx: CommandContext) -> CommandResult:
    """Show or change the Claude model used for this bot.

    Mutates ``ctx.bot_config`` in place and persists via
    ``save_bot_config`` so any adapter holding a closure reference to
    the same dict sees the updated value.
    """

    current_model = ctx.bot_config.get("model", DEFAULT_MODEL)

    if not ctx.args:
        choices = " / ".join(
            f"*{model_display_name(m)}*" if m == current_model else model_display_name(m)
            for m in VALID_MODELS
        )
        text = (
            f"\U0001f9e0 Current model: *{model_display_name(current_model)}*\n\n"
            f"Available: {choices}\n"
            "Usage: `/model sonnet`"
        )
        return CommandResult(text=text)

    new_model = ctx.args[0].lower()
    if not is_valid_model(new_model):
        return CommandResult(
            text=(f"Invalid model: `{new_model}`\nAvailable: {', '.join(VALID_MODELS)}"),
            success=False,
        )

    ctx.bot_config["model"] = new_model
    save_bot_config(ctx.bot_name, ctx.bot_config)
    return CommandResult(
        text=f"\U0001f9e0 Model changed to *{model_display_name(new_model)}*",
    )


async def cmd_streaming(ctx: CommandContext) -> CommandResult:
    """Toggle streaming mode for this bot.

    Mutates ``ctx.bot_config`` so adapters can read the new value
    after the call.
    """

    current = ctx.bot_config.get("streaming", DEFAULT_STREAMING)

    if not ctx.args:
        status_text = "on" if current else "off"
        text = (
            f"\U0001f4e1 Streaming: *{status_text}*\n\nUsage: `/streaming on` or `/streaming off`"
        )
        return CommandResult(text=text)

    value = ctx.args[0].lower()
    if value == "on":
        ctx.bot_config["streaming"] = True
        save_bot_config(ctx.bot_name, ctx.bot_config)
        return CommandResult(text="\U0001f4e1 Streaming enabled.")
    if value == "off":
        ctx.bot_config["streaming"] = False
        save_bot_config(ctx.bot_name, ctx.bot_config)
        return CommandResult(text="\U0001f4e1 Streaming disabled.")
    return CommandResult(
        text="Usage: `/streaming on` or `/streaming off`",
        success=False,
    )


async def cmd_send(ctx: CommandContext) -> CommandResult:
    """Send a workspace file back to the user.

    ``CommandResult.file_path`` is set when a file is selected; the
    adapter then uploads/replies with the file. Without args the
    command returns a usage hint plus the file list.
    """

    session_directory = ensure_session(ctx.bot_path, ctx.chat_id)
    workspace = session_directory / "workspace"

    if not ctx.args:
        files = list_workspace_files(session_directory)
        if not files:
            return CommandResult(
                text="\U0001f4c2 No files in workspace.",
                parse_mode=None,
                success=False,
            )
        file_list = "\n".join(f"  {name}" for name in files)
        return CommandResult(
            text=(f"\U0001f4e4 Usage: `/send filename`\n\nAvailable files:\n```\n{file_list}\n```"),
            success=False,
        )

    filename = " ".join(ctx.args)
    candidate = (workspace / filename).resolve()

    # Path traversal guard: candidate must remain inside ``workspace``.
    try:
        candidate.relative_to(workspace.resolve())
    except ValueError:
        return CommandResult(
            text=f"Invalid path: `{filename}`",
            success=False,
        )

    if not candidate.exists():
        return CommandResult(
            text=f"File not found: `{filename}`",
            success=False,
        )

    if not candidate.is_file():
        return CommandResult(
            text=f"Not a file: `{filename}`",
            success=False,
        )

    return CommandResult(
        text="",
        parse_mode=None,
        file_path=candidate,
    )


# ---------------------------------------------------------------------------
# Cancel — needs runtime cancellation primitives passed in by the adapter
# ---------------------------------------------------------------------------


@dataclass
class CancelOutcome:
    result: CommandResult
    is_group: bool = False
    is_orchestrator: bool = False
    cancelled_bots: list[str] = field(default_factory=list)


async def cmd_cancel(
    ctx: CommandContext,
    *,
    cancel_for: "callable",  # type: ignore[type-arg]
) -> CancelOutcome:
    """Stop the running Claude/SDK task for this session.

    The actual cancellation primitives (backend cancel, SDK session
    cancel, subprocess cancel) live in adapters because they may keep
    different bookkeeping (Telegram vs. dashboard). The caller passes
    an awaitable ``cancel_for(target_bot, session_key) -> bool`` that
    returns ``True`` when something was cancelled.
    """

    group_config = find_group_by_chat_id(ctx.chat_id) if isinstance(ctx.chat_id, int) else None

    if group_config is not None:
        my_role = get_my_role(group_config, ctx.bot_name)
        if my_role != "orchestrator":
            return CancelOutcome(
                result=CommandResult(silent=True),
                is_group=True,
                is_orchestrator=False,
            )

        cancelled: list[str] = []
        if await cancel_for(ctx.bot_name, f"{ctx.bot_name}:{ctx.chat_id}"):
            cancelled.append(ctx.bot_name)
        for member_name in group_config.get("members", []):
            if await cancel_for(member_name, f"{member_name}:{ctx.chat_id}"):
                cancelled.append(member_name)

        if cancelled:
            names = ", ".join(cancelled)
            return CancelOutcome(
                result=CommandResult(text=f"⛔ Cancelled: {names}", parse_mode=None),
                is_group=True,
                is_orchestrator=True,
                cancelled_bots=cancelled,
            )
        return CancelOutcome(
            result=CommandResult(text="No running processes in group.", parse_mode=None),
            is_group=True,
            is_orchestrator=True,
        )

    session_key = f"{ctx.bot_name}:{ctx.chat_id}"
    if await cancel_for(ctx.bot_name, session_key):
        return CancelOutcome(
            result=CommandResult(text="⛔ Execution cancelled.", parse_mode=None),
            cancelled_bots=[ctx.bot_name],
        )
    return CancelOutcome(
        result=CommandResult(text="No running process to cancel.", parse_mode=None),
    )


# ---------------------------------------------------------------------------
# Group binding (Telegram-only — chat_id must be int)
# ---------------------------------------------------------------------------


async def cmd_bind(ctx: CommandContext) -> CommandResult:
    """Bind a group to the current Telegram chat.

    Only the orchestrator processes the bind; other group members
    silently skip via ``CommandResult.silent``. Dashboard sessions
    (``chat_id`` is ``str``) cannot bind: the helper returns a clear
    error rather than corrupting group state.
    """

    if not isinstance(ctx.chat_id, int):
        return CommandResult(
            text="Group bind is only available in Telegram chats.",
            success=False,
            parse_mode=None,
        )

    if not ctx.args:
        return CommandResult(
            text="Usage: `/bind <group_name>`",
            success=False,
        )

    group_name = ctx.args[0]
    group_config = load_group_config(group_name)
    if group_config is None:
        return CommandResult(
            text=f"Group '{group_name}' not found.",
            success=False,
            parse_mode=None,
        )

    role = get_my_role(group_config, ctx.bot_name)
    if role != "orchestrator":
        return CommandResult(silent=True)

    try:
        bind_group(group_name, ctx.chat_id)
    except ValueError as error:
        return CommandResult(
            text=f"Bind failed: {error}",
            success=False,
            parse_mode=None,
        )

    members = ", ".join(group_config.get("members", []))
    return CommandResult(
        text=(f"Group '{group_name}' activated.\nOrchestrator: {ctx.bot_name}\nMembers: {members}"),
        parse_mode=None,
    )


async def cmd_unbind(ctx: CommandContext) -> CommandResult:
    """Remove the group binding from the current Telegram chat."""

    if not isinstance(ctx.chat_id, int):
        return CommandResult(
            text="Group unbind is only available in Telegram chats.",
            success=False,
            parse_mode=None,
        )

    group_config = find_group_by_chat_id(ctx.chat_id)
    if group_config is None:
        return CommandResult(
            text="No group is bound to this chat.",
            parse_mode=None,
            success=False,
        )

    role = get_my_role(group_config, ctx.bot_name)
    if role != "orchestrator":
        return CommandResult(silent=True)

    group_name = group_config["name"]
    unbind_group(group_name)
    return CommandResult(
        text=f"Group '{group_name}' unbound from this chat.",
        parse_mode=None,
    )


# ---------------------------------------------------------------------------
# Skills — list / attach / detach / import
# ---------------------------------------------------------------------------


async def cmd_skills(ctx: CommandContext) -> CommandResult:
    """Manage attached skills for this bot.

    Mutates ``ctx.bot_config["skills"]`` so adapters can refresh their
    closure cache from the same dict reference.
    """

    attached = list(ctx.bot_config.get("skills") or [])

    # Listing (no args): show installed + available + not-installed builtins.
    if not ctx.args:
        from abyss.builtin_skills import list_builtin_skills
        from abyss.skill import list_skills

        installed_skills = list_skills()
        installed_names = {skill["name"] for skill in installed_skills}
        builtin_skills = list_builtin_skills()
        not_installed_builtins = [
            skill for skill in builtin_skills if skill["name"] not in installed_names
        ]

        if not installed_skills and not not_installed_builtins:
            return CommandResult(text="\U0001f9e9 No skills available.", parse_mode=None)

        builtin_names = {skill["name"] for skill in builtin_skills}
        my_skills = set(attached)

        my_attached: list[str] = []
        available: list[str] = []
        not_installed: list[str] = []
        for skill in installed_skills:
            type_display = "builtin" if skill["name"] in builtin_names else "custom"
            if skill["name"] in my_skills:
                my_attached.append(f"✅ `{skill['name']}` ({type_display})")
            else:
                available.append(f"➖ `{skill['name']}` ({type_display})")
        for skill in not_installed_builtins:
            not_installed.append(f"\U0001f4e6 `{skill['name']}` (builtin)")

        lines = ["\U0001f9e9 *Used Skills:*\n"]
        if my_attached:
            lines.extend(my_attached)
        else:
            lines.append("No skills attached.")
        if available:
            lines.append("")
            lines.append("\U0001f4cb *Available:*\n")
            lines.extend(available)
        if not_installed:
            lines.append("")
            lines.append("\U0001f4e6 *Not Installed:*\n")
            lines.extend(not_installed)
        lines.append("")
        lines.append("`/skills attach <name>` | `/skills detach <name>`")
        return CommandResult(text="\n".join(lines))

    subcommand = ctx.args[0].lower()

    if subcommand == "list":
        if not attached:
            return CommandResult(text="\U0001f9e9 No skills attached to this bot.", parse_mode=None)
        skill_list = "\n".join(f"  - {name}" for name in attached)
        return CommandResult(
            text=f"\U0001f9e9 *Attached Skills:*\n```\n{skill_list}\n```",
        )

    if subcommand == "attach":
        if len(ctx.args) < 2:
            return CommandResult(text="Usage: `/skills attach <name>`", success=False)
        from abyss.skill import attach_skill_to_bot, is_skill, skill_status

        skill_name = ctx.args[1]
        if not is_skill(skill_name):
            return CommandResult(
                text=f"Skill '{skill_name}' not found.", parse_mode=None, success=False
            )
        if skill_status(skill_name) == "inactive":
            return CommandResult(
                text=(
                    f"Skill '{skill_name}' is inactive. "
                    f"Run `abyss skills setup {skill_name}` first."
                ),
                success=False,
            )
        if skill_name in attached:
            return CommandResult(
                text=f"Skill '{skill_name}' is already attached.",
                parse_mode=None,
                success=False,
            )
        attach_skill_to_bot(ctx.bot_name, skill_name)
        ctx.bot_config.setdefault("skills", [])
        if skill_name not in ctx.bot_config["skills"]:
            ctx.bot_config["skills"].append(skill_name)
        return CommandResult(text=f"\U0001f9e9 Skill '{skill_name}' attached.", parse_mode=None)

    if subcommand == "detach":
        if len(ctx.args) < 2:
            return CommandResult(text="Usage: `/skills detach <name>`", success=False)
        from abyss.skill import detach_skill_from_bot

        skill_name = ctx.args[1]
        if skill_name not in attached:
            return CommandResult(
                text=f"Skill '{skill_name}' is not attached.",
                parse_mode=None,
                success=False,
            )
        detach_skill_from_bot(ctx.bot_name, skill_name)
        if skill_name in ctx.bot_config.get("skills", []):
            ctx.bot_config["skills"].remove(skill_name)
        return CommandResult(text=f"\U0001f9e9 Skill '{skill_name}' detached.", parse_mode=None)

    if subcommand == "import":
        if len(ctx.args) < 2:
            return CommandResult(text="Usage: `/skills import <github-url>`", success=False)
        from abyss.skill import (
            activate_skill,
            attach_skill_to_bot,
            check_skill_requirements,
            import_skill_from_github,
            parse_github_url,
        )

        github_url = ctx.args[1]
        name_override = ctx.args[2] if len(ctx.args) > 2 else None
        try:
            directory = import_skill_from_github(github_url, name=name_override)
            skill_name = directory.name
            errors = check_skill_requirements(skill_name)
            if not errors:
                activate_skill(skill_name)
        except ValueError as error:
            return CommandResult(text=f"❌ Import failed: {error}", parse_mode=None, success=False)
        except FileExistsError:
            components = parse_github_url(github_url)
            skill_name = name_override or components["repo"]

        if skill_name not in attached:
            attach_skill_to_bot(ctx.bot_name, skill_name)
            ctx.bot_config.setdefault("skills", [])
            if skill_name not in ctx.bot_config["skills"]:
                ctx.bot_config["skills"].append(skill_name)

        return CommandResult(
            text=f"\U0001f9e9 Skill '{skill_name}' imported and attached.",
            parse_mode=None,
        )

    return CommandResult(
        text="Unknown subcommand. Use: list, attach, detach, import",
        parse_mode=None,
        success=False,
    )


# ---------------------------------------------------------------------------
# Heartbeat — status / on / off (``run`` stays adapter-side for now)
# ---------------------------------------------------------------------------


async def cmd_heartbeat_status(ctx: CommandContext) -> CommandResult:
    """Show heartbeat settings for this bot."""

    from abyss.heartbeat import get_heartbeat_config

    heartbeat_config = get_heartbeat_config(ctx.bot_name)
    enabled = heartbeat_config.get("enabled", False)
    interval = heartbeat_config.get("interval_minutes", 30)
    active_hours = heartbeat_config.get("active_hours", {})
    start = active_hours.get("start", "07:00")
    end = active_hours.get("end", "23:00")
    status_text = "on" if enabled else "off"
    text = (
        f"\U0001f493 *Heartbeat Status*\n\n"
        f"Status: *{status_text}*\n"
        f"Interval: {interval}m\n"
        f"Active hours: {start} - {end}\n\n"
        "`/heartbeat on` - Enable\n"
        "`/heartbeat off` - Disable\n"
        "`/heartbeat run` - Run now"
    )
    return CommandResult(text=text)


async def cmd_heartbeat(ctx: CommandContext) -> CommandResult:
    """Dispatch ``/heartbeat`` non-``run`` subcommands.

    ``/heartbeat run`` requires a Telegram ``send_message`` callback to
    deliver the heartbeat message, so the Telegram adapter keeps that
    branch. Dashboards can call ``cmd_heartbeat`` for status/on/off
    and surface a "not yet on dashboard" hint for ``run``.
    """

    from abyss.heartbeat import disable_heartbeat, enable_heartbeat

    if not ctx.args:
        return await cmd_heartbeat_status(ctx)

    subcommand = ctx.args[0].lower()
    if subcommand == "on":
        if enable_heartbeat(ctx.bot_name):
            return CommandResult(text="\U0001f493 Heartbeat enabled.", parse_mode=None)
        return CommandResult(text="Failed to enable heartbeat.", parse_mode=None, success=False)
    if subcommand == "off":
        if disable_heartbeat(ctx.bot_name):
            return CommandResult(text="\U0001f493 Heartbeat disabled.", parse_mode=None)
        return CommandResult(text="Failed to disable heartbeat.", parse_mode=None, success=False)
    if subcommand == "run":
        # ``run`` is platform-specific (needs a per-platform messaging
        # callback). The adapter handles it; this branch is a marker so
        # the dashboard adapter can show a clear message.
        return CommandResult(
            text="Heartbeat run is not supported on this surface.",
            parse_mode=None,
            success=False,
        )

    return CommandResult(
        text="Unknown subcommand. Use: on, off, run",
        parse_mode=None,
        success=False,
    )


# ---------------------------------------------------------------------------
# Compact — show targets + run + persist (Claude-heavy, no streaming hooks)
# ---------------------------------------------------------------------------


@dataclass
class CompactPreview:
    """Result of ``cmd_compact_preview``: a list of target files + a
    human-friendly summary the adapter can show before kicking off the
    long-running compaction."""

    text: str
    targets: list[Any]  # list[CompactTarget]


async def cmd_compact_preview(ctx: CommandContext) -> CompactPreview:
    """Quick pre-compact summary so adapters can warn the user that the
    operation will take a while."""

    from abyss.token_compact import collect_compact_targets

    targets = collect_compact_targets(ctx.bot_name)
    if not targets:
        return CompactPreview(text="No compactable files found.", targets=[])

    target_list = "\n".join(
        f"  - {t.label} ({t.line_count} lines, ~{t.token_count:,} tokens)" for t in targets
    )
    text = f"\U0001f4e6 Found {len(targets)} file(s) to compact:\n{target_list}\n\nCompacting..."
    return CompactPreview(text=text, targets=list(targets))


async def cmd_compact_run(ctx: CommandContext) -> CommandResult:
    """Execute the actual compaction (long-running Claude calls)."""

    from abyss.skill import regenerate_bot_claude_md, update_session_claude_md
    from abyss.token_compact import (
        format_compact_report,
        run_compact,
        save_compact_results,
    )

    model = ctx.bot_config.get("model", DEFAULT_MODEL)
    try:
        results = await run_compact(ctx.bot_name, model=model)
    except Exception as error:  # noqa: BLE001
        return CommandResult(text=f"Compact failed: {error}", parse_mode=None, success=False)

    report = format_compact_report(ctx.bot_name, results)
    successful = [r for r in results if r.error is None]
    if successful:
        save_compact_results(results)
        regenerate_bot_claude_md(ctx.bot_name)
        update_session_claude_md(ctx.bot_path)
        report = f"{report}\n\n✅ Compacted files saved."
    else:
        report = f"{report}\n\nNo files were successfully compacted."
    return CommandResult(text=report, parse_mode=None)


# ---------------------------------------------------------------------------
# Command metadata for adapters (dashboard autocomplete, Telegram BotCommand)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CommandSpec:
    name: str
    description: str
    usage: str = ""


COMMAND_CATALOG: tuple[CommandSpec, ...] = (
    CommandSpec("start", "Bot introduction"),
    CommandSpec("help", "Show available commands"),
    CommandSpec("reset", "Clear conversation (keep workspace)"),
    CommandSpec("resetall", "Delete entire session"),
    CommandSpec("files", "List workspace files"),
    CommandSpec("send", "Send a workspace file back", "/send <filename>"),
    CommandSpec("status", "Session status"),
    CommandSpec("model", "Show or change model", "/model [sonnet|opus|haiku]"),
    CommandSpec("streaming", "Toggle streaming", "/streaming [on|off]"),
    CommandSpec("memory", "Show or clear memory", "/memory [clear]"),
    CommandSpec("skills", "Skill management"),
    CommandSpec("cron", "Cron job management"),
    CommandSpec("heartbeat", "Heartbeat management"),
    CommandSpec("compact", "Compact MD files"),
    CommandSpec("cancel", "Stop running process"),
    CommandSpec("version", "Show abyss version"),
    CommandSpec("bind", "Bind a group to this chat"),
    CommandSpec("unbind", "Remove group binding"),
)


def get_command_spec(name: str) -> CommandSpec | None:
    """Look up command metadata by name."""

    for spec in COMMAND_CATALOG:
        if spec.name == name:
            return spec
    return None
