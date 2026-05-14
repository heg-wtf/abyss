"""Claude Code subprocess runner.

Supports two execution modes:
- SDK mode: Uses Python Agent SDK for session continuity (faster, no process spawn per resume)
- Subprocess mode: Direct `claude -p` invocation (fallback when SDK is unavailable)

The SDK is tried first for resumed sessions; on failure, falls back to subprocess automatically.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 300
STREAMING_CURSOR = "\u258c"

# Tools always allowed when --allowedTools whitelist is active.
# Without these, basic capabilities (web access, shell) get blocked
# when any skill defines allowed_tools.
DEFAULT_ALLOWED_TOOLS = [
    "WebFetch",
    "WebSearch",
    "Bash",
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Agent",
]

# Tracks running processes per session key (e.g. "botname:chat_id")
_running_processes: dict[str, asyncio.subprocess.Process] = {}

# Cached claude path to avoid repeated shutil.which() lookups
_cached_claude_path: str | None = None


def _get_claude_path() -> str:
    """Get the claude CLI path, caching the result."""
    global _cached_claude_path
    if _cached_claude_path is None:
        _cached_claude_path = shutil.which("claude")
    if not _cached_claude_path:
        raise RuntimeError(
            "Claude Code CLI not found. Install: npm install -g @anthropic-ai/claude-code"
        )
    return _cached_claude_path


VALID_EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")


def _effort_flag_args(working_directory: str) -> list[str]:
    """Return ``["--effort", <level>]`` when bot.yaml declares one.

    Reads ``bot.yaml.effort`` (Phase 6 — Claude Code 2.1.111). Invalid
    or missing values yield an empty list so the CLI falls back to its
    own default (``high`` for Pro / Max subscribers on recent models).
    """
    from abyss.config import load_bot_config

    bot_dir = _resolve_bot_dir_from_working_directory(working_directory)
    if bot_dir is None:
        return []
    bot_config = load_bot_config(bot_dir.name) or {}
    raw = bot_config.get("effort")
    if not isinstance(raw, str):
        return []
    level = raw.strip().lower()
    if level not in VALID_EFFORT_LEVELS:
        if level:
            logger.warning(
                "bot %s: invalid effort %r (allowed: %s); skipping --effort",
                bot_dir.name,
                raw,
                ", ".join(VALID_EFFORT_LEVELS),
            )
        return []
    return ["--effort", level]


def _abyss_precompact_hook_entry() -> dict[str, Any]:
    """Build the PreCompact hook entry pointing at abyss's hook script.

    The session settings file is the canonical place for hooks (deeper
    than bot- or home-level settings, so it wins on merge). We inject
    the entry here so abyss can react to Claude Code's PreCompact event
    by compacting MEMORY.md / HEARTBEAT.md / user SKILL.md files —
    wherever the host decides the conversation is heavy enough.
    """
    import sys

    command = f"{sys.executable} -m abyss.hooks.precompact_hook"
    return {"matcher": "", "hooks": [{"type": "command", "command": command}]}


def _abyss_posttooluse_hook_entry(outcome: str = "success") -> dict[str, Any]:
    """Build the PostToolUse / PostToolUseFailure hook entry.

    Claude Code 2.1.119 surfaces ``duration_ms`` on PostToolUse payloads,
    but failed tool executions land on ``PostToolUseFailure`` instead.
    Register the hook on both events so abyss captures every call.
    ``ABYSS_HOOK_OUTCOME`` lets the hook script tag the event without
    parsing the payload schema differences between the two channels.

    abyss's hook (``abyss.hooks.log_tool_metrics``) appends one JSONL
    event per tool call so abysscope can graph latency without a DB.
    Matcher is ``*`` to capture every tool.
    """
    import shlex
    import sys

    command = (
        f"ABYSS_HOOK_OUTCOME={shlex.quote(outcome)} "
        f"{sys.executable} -m abyss.hooks.log_tool_metrics"
    )
    return {"matcher": "*", "hooks": [{"type": "command", "command": command}]}


def _merge_skill_hooks(
    working_directory: str,
    event_name: str,
    existing: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Append skill-declared hook entries to the baseline list.

    Each attached skill may declare ``hooks.<EventName>`` in its
    ``skill.yaml`` (Claude Code event names: ``PreToolUse``, ``PostToolUse``,
    ``PreCompact``, etc.). Entries can use the ``if`` field added in
    Claude Code 2.1.85 for conditional firing — abyss writes the field
    through verbatim.
    """
    from abyss.config import load_bot_config

    bot_dir = _resolve_bot_dir_from_working_directory(working_directory)
    if bot_dir is None:
        return existing

    bot_config = load_bot_config(bot_dir.name) or {}
    skill_names = bot_config.get("skills") or []
    if not skill_names:
        return existing

    from abyss.skill import collect_skill_hooks

    skill_entries = collect_skill_hooks(skill_names, event_name)
    return existing + skill_entries


def _hooks_enabled_for_working_directory(working_directory: str) -> bool:
    """Return whether abyss should inject hooks for the given session.

    Walks up to the bot directory, loads ``bot.yaml`` and reads the
    ``hooks_enabled`` toggle. Default ``True``. Returns ``True`` even
    when the bot directory cannot be resolved (e.g. test fixtures using
    ``/tmp``) so unit tests still exercise the injection path.
    """
    from abyss.config import load_bot_config

    bot_dir = _resolve_bot_dir_from_working_directory(working_directory)
    if bot_dir is None:
        return True

    bot_config = load_bot_config(bot_dir.name) or {}
    return bool(bot_config.get("hooks_enabled", True))


def _write_session_settings(working_directory: str, allowed_tools: list[str]) -> None:
    """Write .claude/settings.json in the session directory.

    Always writes when invoked (no longer conditional on ``allowed_tools``
    being non-empty) so abyss can install its PreCompact hook even for
    bots without skills. ``allowed_tools`` may be empty — in that case
    the ``permissions`` section is omitted.
    """
    claude_directory = Path(working_directory) / ".claude"
    claude_directory.mkdir(parents=True, exist_ok=True)

    settings_path = claude_directory / "settings.json"

    settings: dict[str, Any] = {}
    if settings_path.exists():
        with open(settings_path) as settings_file:
            settings = json.load(settings_file)

    if allowed_tools:
        permissions = settings.get("permissions", {})
        existing_allow = set(permissions.get("allow", []))
        existing_allow.update(allowed_tools)
        permissions["allow"] = sorted(existing_allow)
        settings["permissions"] = permissions

    # Hooks: start from a clean slate per session so a stray entry in
    # ~/.claude/settings.json (user global) cannot fire for bot
    # subprocesses. Then inject abyss's own PreCompact hook when the
    # bot has not opted out via bot.yaml `hooks_enabled: false`.
    if "hooks" not in settings or not isinstance(settings["hooks"], dict):
        settings["hooks"] = {}

    if _hooks_enabled_for_working_directory(working_directory):
        settings["hooks"]["PreCompact"] = [_abyss_precompact_hook_entry()]
        # PostToolUse fires only on success; failures land on
        # PostToolUseFailure (CC docs). Register both so the metrics
        # log doesn't underreport errors. Skill-supplied entries are
        # appended after the abyss baseline on each event.
        settings["hooks"]["PostToolUse"] = _merge_skill_hooks(
            working_directory,
            "PostToolUse",
            existing=[_abyss_posttooluse_hook_entry("success")],
        )
        settings["hooks"]["PostToolUseFailure"] = _merge_skill_hooks(
            working_directory,
            "PostToolUseFailure",
            existing=[_abyss_posttooluse_hook_entry("failure")],
        )
    else:
        settings["hooks"].pop("PreCompact", None)
        settings["hooks"].pop("PostToolUse", None)
        settings["hooks"].pop("PostToolUseFailure", None)

    # Disable all plugins for bot subprocess sessions.
    # Plugin hooks (e.g. context-mode) are loaded from
    # ~/.claude/plugins/ and are NOT overridden by the
    # hooks: {} above. Bots run autonomously and should
    # not inherit interactive-session plugins.
    if "enabledPlugins" not in settings:
        settings["enabledPlugins"] = {}

    # Phase 5: security hardening.
    # 1. ``disableSkillShellExecution`` (CC 2.1.91): block ``!command``
    #    blocks from running when any attached skill is untrusted
    #    (e.g. imported from a third-party GitHub repo).
    # 2. ``sandbox.network.deniedDomains`` (CC 2.1.113): refuse outbound
    #    traffic to cloud-metadata endpoints by default; merge per-bot
    #    extras from ``bot.yaml.sandbox.denied_domains``.
    _apply_security_settings(working_directory, settings)

    with open(settings_path, "w") as settings_file:
        json.dump(settings, settings_file, indent=2)


def _apply_security_settings(working_directory: str, settings: dict[str, Any]) -> None:
    """Mutate ``settings`` with Phase 5 security blocks.

    Resolves the bot from ``working_directory`` and pulls
    ``has_untrusted_skill`` + ``compose_bot_sandbox`` to populate the
    relevant settings.json keys. Falls back to defaults when the bot
    directory cannot be resolved (test fixtures using ``/tmp``).
    """
    from abyss.config import compose_bot_sandbox, load_bot_config
    from abyss.skill import has_untrusted_skill

    bot_config: dict[str, Any] | None = None
    bot_dir = _resolve_bot_dir_from_working_directory(working_directory)
    if bot_dir is not None:
        bot_config = load_bot_config(bot_dir.name)

    skill_names = []
    if isinstance(bot_config, dict):
        raw_skills = bot_config.get("skills")
        if isinstance(raw_skills, list):
            skill_names = [name for name in raw_skills if isinstance(name, str)]

    settings["disableSkillShellExecution"] = has_untrusted_skill(skill_names)
    settings["sandbox"] = compose_bot_sandbox(bot_config)


def register_process(session_key: str, process: asyncio.subprocess.Process) -> None:
    """Register a running process for a session."""
    _running_processes[session_key] = process


def unregister_process(session_key: str) -> None:
    """Unregister a process for a session."""
    _running_processes.pop(session_key, None)


def cancel_process(session_key: str) -> bool:
    """Cancel a running process for a session.

    Returns True if a process was found and killed, False otherwise.
    """
    process = _running_processes.get(session_key)
    if process and process.returncode is None:
        process.kill()
        logger.info("Cancelled Claude Code process for session %s", session_key)
        return True
    return False


def cancel_all_processes() -> int:
    """Kill all running Claude Code subprocesses.

    Called during shutdown to avoid waiting for long-running processes.
    Returns the number of processes killed.
    """
    killed = 0
    for session_key, process in list(_running_processes.items()):
        if process.returncode is None:
            process.kill()
            logger.info("Shutdown: killed process for session %s", session_key)
            killed += 1
    _running_processes.clear()
    return killed


def is_process_running(session_key: str) -> bool:
    """Check if a process is currently running for a session."""
    process = _running_processes.get(session_key)
    return process is not None and process.returncode is None


async def run_claude(
    working_directory: str,
    message: str,
    extra_arguments: list[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    session_key: str | None = None,
    model: str | None = None,
    skill_names: list[str] | None = None,
    claude_session_id: str | None = None,
    resume_session: bool = False,
) -> str:
    """Run Claude Code CLI as a subprocess and return its output.

    Args:
        working_directory: Working directory for Claude Code.
        message: The prompt message to send.
        extra_arguments: Additional CLI arguments from bot config.
        timeout: Maximum execution time in seconds.
        session_key: Optional key for process tracking (enables /cancel).
        model: Claude model to use (sonnet, opus, haiku).
        skill_names: Optional list of skill names to inject MCP config and env vars.
        claude_session_id: Optional Claude Code session ID for continuity.
        resume_session: If True and claude_session_id is set, use --resume instead of --session-id.

    Returns:
        The text output from Claude Code.

    Raises:
        TimeoutError: If execution exceeds timeout.
        RuntimeError: If Claude Code returns a non-zero exit code.
        asyncio.CancelledError: If the process was cancelled via cancel_process.
    """
    claude_path = _get_claude_path()

    command = [
        claude_path,
        "-p",
        message,
        "--output-format",
        "text",
    ]

    if resume_session and claude_session_id:
        command.extend(["--resume", claude_session_id])
    elif claude_session_id:
        command.extend(["--session-id", claude_session_id])

    if model:
        command.extend(["--model", model])

    # Phase 6: bot.yaml.effort -> --effort <level>
    command.extend(_effort_flag_args(working_directory))

    if extra_arguments:
        command.extend(extra_arguments)

    # Inject MCP config and environment variables from skills
    allowed_tools, environment = _prepare_skill_config(working_directory, skill_names)
    if allowed_tools:
        command.extend(["--allowedTools", ",".join(allowed_tools)])

    logger.info("Running claude in %s: %s", working_directory, message[:100])

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=working_directory,
        env=environment,
    )

    if session_key:
        register_process(session_key, process)

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        logger.error("Claude Code timed out after %ds", timeout)
        raise TimeoutError(f"Claude Code timed out after {timeout} seconds")
    finally:
        if session_key:
            unregister_process(session_key)

    if process.returncode == -9:
        raise asyncio.CancelledError("Claude Code was cancelled")

    output = stdout.decode("utf-8", errors="replace").strip()
    error_output = stderr.decode("utf-8", errors="replace").strip()

    if process.returncode != 0:
        logger.error("Claude Code failed (rc=%d): %s", process.returncode, error_output)
        raise RuntimeError(f"Claude Code exited with code {process.returncode}: {error_output}")

    if error_output:
        logger.warning("Claude Code stderr: %s", error_output[:200])

    return output


async def run_ultrareview(
    target: str,
    working_directory: str,
    *,
    json_output: bool = True,
    timeout: int = 1800,
    extra_arguments: list[str] | None = None,
) -> str:
    """Invoke ``claude ultrareview <target>`` non-interactively.

    Phase 6 — Claude Code 2.1.120 added ``claude ultrareview`` as a
    standalone subcommand that runs the comprehensive parallel code
    review pipeline against a PR (URL / number) or a local path. abyss
    wraps it so a Telegram message like "review PR #123" can fan out
    to the same review the human-side ``/ultrareview`` skill would run.

    Args:
        target: PR URL, PR number, or path. Passed verbatim to the CLI.
        working_directory: Working directory for the review (the repo).
        json_output: Pass ``--json`` to receive the structured payload
            (default). When ``False`` the human-readable text is returned.
        timeout: Seconds before the process is killed. CC's own default
            is 30 minutes; we use 1800s to match. Pass ``--timeout`` via
            ``extra_arguments`` to override on the CLI side too.
        extra_arguments: Additional CLI flags passed through verbatim.

    Returns:
        stdout from the ultrareview run.

    Raises:
        TimeoutError: process killed after ``timeout`` seconds.
        RuntimeError: ultrareview exited non-zero.
        ValueError: ``target`` is empty / non-string.
    """
    if not isinstance(target, str) or not target.strip():
        raise ValueError("ultrareview target must be a non-empty string")

    claude_path = _get_claude_path()
    command = [claude_path, "ultrareview", target.strip()]
    if json_output:
        command.append("--json")
    if extra_arguments:
        command.extend(extra_arguments)

    # Apply Phase 1 env (1h cache, AI_AGENT, hide_cwd, etc.) so the
    # subprocess inherits the same hardening abyss applies elsewhere.
    from abyss.config import apply_claude_code_env

    environment = apply_claude_code_env(dict(os.environ))

    logger.info("Running claude ultrareview in %s on target %r", working_directory, target)

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=working_directory,
        env=environment,
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        logger.error("ultrareview timed out after %ds", timeout)
        raise TimeoutError(f"ultrareview timed out after {timeout} seconds")

    output = stdout.decode("utf-8", errors="replace").strip()
    error_output = stderr.decode("utf-8", errors="replace").strip()

    if process.returncode != 0:
        logger.error("ultrareview failed (rc=%d): %s", process.returncode, error_output[:300])
        raise RuntimeError(f"ultrareview exited with code {process.returncode}: {error_output}")

    if error_output:
        logger.warning("ultrareview stderr: %s", error_output[:200])

    return output


QMD_MCP_SERVER = {"qmd": {"type": "http", "url": "http://localhost:8181/mcp"}}


def _qmd_mcp_server(always_load: bool) -> dict[str, dict]:
    """Return the QMD MCP entry, optionally tagged ``alwaysLoad``.

    ``alwaysLoad`` is a Claude Code 2.1.121 option that pre-connects the
    MCP server at host startup. Only applied when the abyss config
    toggle ``mcp_always_load`` is on.
    """
    entry = {"type": "http", "url": "http://localhost:8181/mcp"}
    if always_load:
        entry["alwaysLoad"] = True
    return {"qmd": entry}


QMD_ALLOWED_TOOLS = [
    "mcp__qmd__search",
    "mcp__qmd__vector_search",
    "mcp__qmd__deep_search",
    "mcp__qmd__get",
    "mcp__qmd__multi_get",
    "mcp__qmd__status",
]

CONVERSATION_SEARCH_ALLOWED_TOOLS = [
    "mcp__conversation_search__search_conversations",
]


def _resolve_bot_dir_from_working_directory(working_directory: str) -> Path | None:
    """Walk parents of ``working_directory`` to find the bot root.

    The bot root is the directory whose parent is named ``bots`` — this
    works regardless of which subfolder the call originated from
    (``sessions/chat_*``, ``cron_sessions/<job>``, ``heartbeat_sessions``).
    Returns ``None`` when no such ancestor exists (e.g., test
    environments using ``/tmp`` paths).
    """
    work_path = Path(working_directory).resolve()
    candidates = [work_path, *work_path.parents]
    for candidate in candidates:
        parent = candidate.parent
        if parent.name == "bots":
            return candidate
    return None


def _conversation_search_mcp_server(working_directory: str) -> dict | None:
    """Build the conversation_search MCP entry for ``working_directory``.

    Resolves the bot directory by walking up the working-directory tree
    until a ``bots/<name>/`` ancestor is found. This works for DM
    sessions (``bots/<name>/sessions/chat_*/``), cron sessions
    (``bots/<name>/cron_sessions/<job>/``) and heartbeat sessions
    (``bots/<name>/heartbeat_sessions/``) alike. Returns ``None`` when
    the bot root cannot be located so the caller skips the MCP entry.
    """
    import sys

    bot_dir = _resolve_bot_dir_from_working_directory(working_directory)
    if bot_dir is None:
        return None

    from abyss.config import is_mcp_always_load_enabled

    db_path = bot_dir / "conversation.db"
    entry: dict = {
        "command": sys.executable,
        "args": ["-m", "abyss.mcp_servers.conversation_search"],
        "env": {"ABYSS_CONVERSATION_DB": str(db_path)},
    }
    if is_mcp_always_load_enabled():
        entry["alwaysLoad"] = True
    return {"conversation_search": entry}


def _prepare_skill_config(
    working_directory: str,
    skill_names: list[str] | None,
) -> tuple[list[str] | None, dict[str, str] | None]:
    """Prepare MCP config, settings, and environment variables for skills.

    Writes .mcp.json and .claude/settings.json to the working directory.
    Returns (allowed_tools, environment_variables).

    Also auto-injects QMD MCP config if QMD CLI is available on the system,
    regardless of whether the bot has the qmd skill attached, and
    auto-injects the conversation_search MCP server when SQLite FTS5 is
    available.
    """
    from abyss.skill import (
        collect_skill_allowed_tools,
        collect_skill_environment_variables,
        merge_mcp_configs,
    )

    work_path = Path(working_directory)
    if not work_path.is_dir():
        # Without a real session directory we cannot safely write
        # .mcp.json or settings.json. Production callers always create
        # the directory first; this guard keeps unit tests that pass
        # placeholder paths from blowing up on the auto-injected MCP
        # config write.
        logger.debug(
            "skipping skill config; working_directory missing: %s",
            working_directory,
        )
        return None, None

    from abyss.config import apply_claude_code_env

    mcp_config = None
    allowed_tools: list[str] = []

    # Always apply Claude Code feature env vars (prompt caching, fork
    # subagent, MCP nonblocking, hide cwd, AI_AGENT). Disabled toggles
    # explicitly remove the corresponding host-shell export so that a
    # ``false`` in config.yaml cannot be silently overridden by a stray
    # variable inherited from the user's shell profile. Skill env vars
    # override these when keys collide.
    environment_variables: dict[str, str] = apply_claude_code_env(dict(os.environ))

    # Process attached skills
    if skill_names:
        mcp_config = merge_mcp_configs(skill_names)

        skill_environment_variables = collect_skill_environment_variables(skill_names)
        if skill_environment_variables:
            environment_variables = {**environment_variables, **skill_environment_variables}

        allowed_tools = collect_skill_allowed_tools(skill_names)

    # Auto-inject QMD MCP if CLI is available (system-wide, all bots)
    if shutil.which("qmd"):
        from abyss.config import is_mcp_always_load_enabled

        qmd_entry = _qmd_mcp_server(is_mcp_always_load_enabled())
        if mcp_config:
            mcp_config["mcpServers"].update(qmd_entry)
        else:
            mcp_config = {"mcpServers": dict(qmd_entry)}
        for tool in QMD_ALLOWED_TOOLS:
            if tool not in allowed_tools:
                allowed_tools.append(tool)

    # Auto-inject conversation_search MCP when the local SQLite supports
    # FTS5 (effectively always on macOS / Linux).
    from abyss.conversation_index import is_fts5_available

    if is_fts5_available():
        cs_server = _conversation_search_mcp_server(working_directory)
        if cs_server is not None:
            if mcp_config:
                mcp_config["mcpServers"].update(cs_server)
            else:
                mcp_config = {"mcpServers": dict(cs_server)}
            for tool in CONVERSATION_SEARCH_ALLOWED_TOOLS:
                if tool not in allowed_tools:
                    allowed_tools.append(tool)

    # Write MCP config file
    if mcp_config:
        mcp_json_path = str(Path(working_directory) / ".mcp.json")
        with open(mcp_json_path, "w") as mcp_file:
            json.dump(mcp_config, mcp_file, indent=2)

    # Merge default tools when whitelist is active
    if allowed_tools:
        for tool in DEFAULT_ALLOWED_TOOLS:
            if tool not in allowed_tools:
                allowed_tools.append(tool)
        logger.info("Allowed tools: %s", allowed_tools)

    # Always write session settings — even when no tools are whitelisted —
    # so abyss can install its PreCompact hook (Phase 3).
    _write_session_settings(working_directory, allowed_tools)

    return allowed_tools or None, environment_variables


def _extract_text_delta(data: dict[str, Any]) -> str | None:
    """Extract text from a stream-json event line.

    Handles two event types:
    - stream_event with content_block_delta (token-level, --verbose mode)
    - assistant message with text content blocks (turn-level)
    """
    event_type = data.get("type")

    if event_type == "stream_event":
        event = data.get("event", {})
        if event.get("type") == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                return delta.get("text", "")

    return None


def _extract_result_text(data: dict[str, Any]) -> str | None:
    """Extract the final result text from a result event."""
    if data.get("type") == "result":
        return data.get("result")
    return None


def _extract_assistant_text(data: dict[str, Any]) -> str | None:
    """Extract text from an assistant turn-level event (non-verbose mode)."""
    if data.get("type") == "assistant":
        message = data.get("message", {})
        content_blocks = message.get("content", [])
        texts = []
        for block in content_blocks:
            if block.get("type") == "text":
                texts.append(block.get("text", ""))
        if texts:
            return "".join(texts)
    return None


async def run_claude_streaming(
    working_directory: str,
    message: str,
    on_text_chunk: Callable[[str], Any] | None = None,
    extra_arguments: list[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    session_key: str | None = None,
    model: str | None = None,
    skill_names: list[str] | None = None,
    claude_session_id: str | None = None,
    resume_session: bool = False,
) -> str:
    """Run Claude Code CLI with streaming output.

    Uses --output-format stream-json --verbose --include-partial-messages
    to receive token-level text deltas. Calls on_text_chunk for each text
    chunk received. Returns the final complete text.

    If stream-json produces no result, falls back to accumulated text
    from streaming deltas or assistant turn events.

    Args:
        working_directory: Working directory for Claude Code.
        message: The prompt message to send.
        on_text_chunk: Async or sync callback for each text chunk.
        extra_arguments: Additional CLI arguments from bot config.
        timeout: Maximum execution time in seconds.
        session_key: Optional key for process tracking (enables /cancel).
        model: Claude model to use (sonnet, opus, haiku).
        skill_names: Optional list of skill names to inject MCP config and env vars.
        claude_session_id: Optional Claude Code session ID for continuity.
        resume_session: If True and claude_session_id is set, use --resume instead of --session-id.

    Returns:
        The complete text output from Claude Code.

    Raises:
        TimeoutError: If execution exceeds timeout.
        RuntimeError: If Claude Code returns a non-zero exit code.
        asyncio.CancelledError: If the process was cancelled via cancel_process.
    """
    claude_path = _get_claude_path()

    command = [
        claude_path,
        "-p",
        message,
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
    ]

    if resume_session and claude_session_id:
        command.extend(["--resume", claude_session_id])
    elif claude_session_id:
        command.extend(["--session-id", claude_session_id])

    if model:
        command.extend(["--model", model])

    # Phase 6: bot.yaml.effort -> --effort <level>
    command.extend(_effort_flag_args(working_directory))

    if extra_arguments:
        command.extend(extra_arguments)

    allowed_tools, environment = _prepare_skill_config(working_directory, skill_names)
    if allowed_tools:
        command.extend(["--allowedTools", ",".join(allowed_tools)])

    logger.info(
        "Running claude (streaming) in %s: %s",
        working_directory,
        message[:100],
    )

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=working_directory,
        env=environment,
    )

    if session_key:
        register_process(session_key, process)

    accumulated_text = ""
    result_text: str | None = None

    async def read_stream() -> None:
        nonlocal accumulated_text, result_text

        while True:
            line = await process.stdout.readline()
            if not line:
                break

            line_text = line.decode("utf-8", errors="replace").strip()
            if not line_text:
                continue

            try:
                data = json.loads(line_text)
            except json.JSONDecodeError:
                logger.debug("Non-JSON line from stream: %s", line_text[:100])
                continue

            # Check for text delta (token-level streaming)
            text_delta = _extract_text_delta(data)
            if text_delta is not None:
                accumulated_text += text_delta
                if on_text_chunk and text_delta:
                    try:
                        result = on_text_chunk(text_delta)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as callback_error:
                        logger.debug(
                            "Stream chunk callback error: %s",
                            callback_error,
                        )

            # Check for assistant turn text (fallback for non-verbose)
            assistant_text = _extract_assistant_text(data)
            if assistant_text is not None and not accumulated_text:
                accumulated_text = assistant_text
                if on_text_chunk:
                    with suppress(Exception):
                        result = on_text_chunk(assistant_text)
                        if asyncio.iscoroutine(result):
                            await result

            # Check for final result
            final = _extract_result_text(data)
            if final is not None:
                result_text = final

    try:
        await asyncio.wait_for(read_stream(), timeout=timeout)
        await process.wait()
    except asyncio.TimeoutError:
        process.kill()
        with suppress(Exception):
            await process.communicate()
        logger.error("Claude Code (streaming) timed out after %ds", timeout)
        raise TimeoutError(f"Claude Code timed out after {timeout} seconds")
    finally:
        if session_key:
            unregister_process(session_key)

    if process.returncode == -9:
        raise asyncio.CancelledError("Claude Code was cancelled")

    # Read any remaining stderr
    stderr_data = b""
    if process.stderr:
        with suppress(Exception):
            stderr_data = await process.stderr.read()
    error_output = stderr_data.decode("utf-8", errors="replace").strip()

    if process.returncode != 0:
        logger.error(
            "Claude Code (streaming) failed (rc=%d): %s",
            process.returncode,
            error_output,
        )
        raise RuntimeError(f"Claude Code exited with code {process.returncode}: {error_output}")

    if error_output:
        logger.warning("Claude Code stderr: %s", error_output[:200])

    # Prefer result event text, fall back to accumulated streaming text
    final_text = result_text if result_text is not None else accumulated_text
    return final_text.strip()


# ─── SDK-aware wrappers ─────────────────────────────────────────────────────


async def run_claude_with_sdk(
    working_directory: str,
    message: str,
    extra_arguments: list[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    session_key: str | None = None,
    model: str | None = None,
    skill_names: list[str] | None = None,
    claude_session_id: str | None = None,
    resume_session: bool = False,
    session_directory: Path | None = None,
) -> str:
    """Run Claude Code, trying the SDK pool first, falling back to subprocess.

    Uses the persistent SDK pool for all messages when available. The pool keeps
    a ``ClaudeSDKClient`` per session_key, avoiding process re-spawn on follow-up
    messages. Falls back to subprocess when the SDK is unavailable or on error.

    Args:
        session_directory: If provided, session_id is auto-loaded/saved from
            ``.claude_session_id`` in this directory.
    """
    from abyss.sdk_client import get_pool, is_sdk_available
    from abyss.session import get_claude_session_id, save_claude_session_id

    if session_key and is_sdk_available():
        try:
            allowed_tools, environment_variables = _prepare_skill_config(
                working_directory, skill_names
            )
            pool = get_pool()

            # Load saved session_id for resume (only when creating a new client)
            saved_session_id = (
                get_claude_session_id(session_directory)
                if session_directory and not pool.has_session(session_key)
                else None
            )

            logger.info("Running claude via SDK pool for %s: %s", session_key, message[:100])

            result = await pool.query(
                session_key=session_key,
                prompt=message,
                working_directory=working_directory,
                model=model,
                allowed_tools=allowed_tools,
                environment_variables=environment_variables,
                resume_session_id=saved_session_id,
                timeout=timeout,
            )

            if session_directory and result.session_id:
                save_claude_session_id(session_directory, result.session_id)

            return result.text
        except (ConnectionError, OSError) as error:
            logger.warning("SDK pool unavailable, falling back to subprocess: %s", error)
        except Exception as error:
            logger.warning("SDK pool query failed, falling back to subprocess: %s", error)
            # Remove broken session from pool
            from abyss.sdk_client import get_pool as _get_pool

            pool = _get_pool()
            await pool.close_session(session_key)

    # Fallback to direct subprocess
    return await run_claude(
        working_directory=working_directory,
        message=message,
        extra_arguments=extra_arguments,
        timeout=timeout,
        session_key=session_key,
        model=model,
        skill_names=skill_names,
        claude_session_id=claude_session_id,
        resume_session=resume_session,
    )


async def run_claude_streaming_with_sdk(
    working_directory: str,
    message: str,
    on_text_chunk: Callable[[str], Any] | None = None,
    extra_arguments: list[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    session_key: str | None = None,
    model: str | None = None,
    skill_names: list[str] | None = None,
    claude_session_id: str | None = None,
    resume_session: bool = False,
    session_directory: Path | None = None,
) -> str:
    """Run Claude Code with streaming, trying SDK pool first.

    Uses the persistent SDK pool for streaming. Falls back to subprocess
    streaming when the SDK is unavailable or on error.

    Args:
        session_directory: If provided, session_id is auto-loaded/saved from
            ``.claude_session_id`` in this directory.
    """
    from abyss.sdk_client import get_pool, is_sdk_available
    from abyss.session import get_claude_session_id, save_claude_session_id

    if session_key and is_sdk_available():
        try:
            allowed_tools, environment_variables = _prepare_skill_config(
                working_directory, skill_names
            )
            pool = get_pool()

            saved_session_id = (
                get_claude_session_id(session_directory)
                if session_directory and not pool.has_session(session_key)
                else None
            )

            logger.info(
                "Running claude (streaming) via SDK pool for %s: %s",
                session_key,
                message[:100],
            )

            result = await pool.query_streaming(
                session_key=session_key,
                prompt=message,
                on_text_chunk=on_text_chunk,
                working_directory=working_directory,
                model=model,
                allowed_tools=allowed_tools,
                environment_variables=environment_variables,
                resume_session_id=saved_session_id,
                timeout=timeout,
            )

            if session_directory and result.session_id:
                save_claude_session_id(session_directory, result.session_id)

            return result.text
        except (ConnectionError, OSError) as error:
            logger.warning(
                "SDK pool unavailable (streaming), falling back to subprocess: %s",
                error,
            )
        except Exception as error:
            logger.warning("SDK pool streaming failed, falling back to subprocess: %s", error)
            from abyss.sdk_client import get_pool as _get_pool

            pool = _get_pool()
            await pool.close_session(session_key)

    # Fallback to direct subprocess streaming
    return await run_claude_streaming(
        working_directory=working_directory,
        message=message,
        on_text_chunk=on_text_chunk,
        extra_arguments=extra_arguments,
        timeout=timeout,
        session_key=session_key,
        model=model,
        skill_names=skill_names,
        claude_session_id=claude_session_id,
        resume_session=resume_session,
    )


async def cancel_sdk_session(session_key: str) -> bool:
    """Interrupt a running SDK pool session.

    Returns True if a session was found and interrupted, False otherwise.
    """
    from abyss.sdk_client import get_pool, is_sdk_available

    if not is_sdk_available():
        return False

    pool = get_pool()
    if not pool.has_session(session_key):
        return False

    return await pool.interrupt(session_key)
