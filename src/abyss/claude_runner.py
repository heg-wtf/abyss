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
from contextlib import suppress
from pathlib import Path
from typing import Any, Callable

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


def _write_session_settings(working_directory: str, allowed_tools: list[str]) -> None:
    """Write .claude/settings.json in the session directory with skill permissions."""
    if not allowed_tools:
        return

    claude_directory = Path(working_directory) / ".claude"
    claude_directory.mkdir(parents=True, exist_ok=True)

    settings_path = claude_directory / "settings.json"

    settings: dict[str, Any] = {}
    if settings_path.exists():
        with open(settings_path) as settings_file:
            settings = json.load(settings_file)

    permissions = settings.get("permissions", {})
    existing_allow = set(permissions.get("allow", []))
    existing_allow.update(allowed_tools)

    permissions["allow"] = sorted(existing_allow)
    settings["permissions"] = permissions

    # Disable hooks inherited from ~/.claude/settings.json
    # to prevent user-level plugins (e.g. context-mode) from
    # interfering with bot's claude -p subprocess.
    if "hooks" not in settings:
        settings["hooks"] = {}

    # Disable all plugins for bot subprocess sessions.
    # Plugin hooks (e.g. context-mode) are loaded from
    # ~/.claude/plugins/ and are NOT overridden by the
    # hooks: {} above. Bots run autonomously and should
    # not inherit interactive-session plugins.
    if "enabledPlugins" not in settings:
        settings["enabledPlugins"] = {}

    with open(settings_path, "w") as settings_file:
        json.dump(settings, settings_file, indent=2)


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


QMD_MCP_SERVER = {"qmd": {"type": "http", "url": "http://localhost:8181/mcp"}}
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


def _conversation_search_mcp_server(working_directory: str) -> dict | None:
    """Build the conversation_search MCP entry for ``working_directory``.

    Returns ``None`` when the working directory does not look like a bot
    session path (we expect ``<bot_dir>/sessions/chat_*/`` so the bot dir
    is at ``parents[1]``). The MCP server is invoked via ``sys.executable``
    so it inherits the abyss venv and can ``import abyss``.
    """
    import sys

    work_path = Path(working_directory).resolve()
    try:
        bot_dir = work_path.parents[1]
    except IndexError:
        return None

    db_path = bot_dir / "conversation.db"
    return {
        "conversation_search": {
            "command": sys.executable,
            "args": ["-m", "abyss.mcp_servers.conversation_search"],
            "env": {"ABYSS_CONVERSATION_DB": str(db_path)},
        }
    }


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

    mcp_config = None
    allowed_tools: list[str] = []
    environment_variables = None

    # Process attached skills
    if skill_names:
        mcp_config = merge_mcp_configs(skill_names)

        skill_environment_variables = collect_skill_environment_variables(skill_names)
        if skill_environment_variables:
            environment_variables = {**os.environ, **skill_environment_variables}

        allowed_tools = collect_skill_allowed_tools(skill_names)

    # Auto-inject QMD MCP if CLI is available (system-wide, all bots)
    if shutil.which("qmd"):
        if mcp_config:
            mcp_config["mcpServers"].update(QMD_MCP_SERVER)
        else:
            mcp_config = {"mcpServers": dict(QMD_MCP_SERVER)}
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
        _write_session_settings(working_directory, allowed_tools)
        logger.info("Allowed tools: %s", allowed_tools)

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
