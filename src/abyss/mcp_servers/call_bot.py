"""MCP stdio server letting a bot call another bot's LLM in fresh context.

Phase 7.0 of the co-evolution roadmap. One tool — ``call_bot(name, message,
timeout?)``.

The peer bot runs through ``llm.registry.get_or_create`` (same SDK pool
as chat / cron) with a per-call ``session_key`` so each invocation is
fresh — peer has its own personality / MEMORY / SELF / facts / skills
from disk, but no accumulated dialog with this caller.

Depth guard: ``ABYSS_CALL_BOT_DEPTH`` env var increments on each
nested call. Refuses to recurse past ``MAX_DEPTH`` so a cycle
(A → B → A → ...) can't burn unbounded tokens. The env is propagated
to the peer LLMRequest so even peer-spawned tools see the same
depth counter.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "abyss-call-bot"
SERVER_VERSION = "1.0.0"

MAX_RESULT_SIZE_CHARS = 200_000
RESULT_META: dict[str, Any] = {"anthropic/maxResultSizeChars": MAX_RESULT_SIZE_CHARS}

DEPTH_ENV = "ABYSS_CALL_BOT_DEPTH"
MAX_DEPTH = 3
MAX_MESSAGE_BYTES = 4096
DEFAULT_TIMEOUT_SECONDS = 120.0


# ─── tool definition ──────────────────────────────────────────────────────


CALL_BOT_TOOL: dict[str, Any] = {
    "name": "call_bot",
    "description": (
        "Ask a different abyss bot to answer ``message`` and return "
        "its raw reply. Use this when you need another bot's "
        "personality, memory, or specialised skills (e.g. ask the "
        "finance bot about a Stripe invoice). The peer answers with "
        "its own CLAUDE.md / MEMORY / SELF / facts / skills — you "
        "don't see those, you only get the prose reply. "
        "Quote the peer's reply in your own answer rather than "
        "pretending you wrote it. Do NOT call this in a loop — "
        "depth is capped at 3 to prevent runaway cost."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "bot": {
                "type": "string",
                "description": "Name of the peer bot to call.",
            },
            "message": {
                "type": "string",
                "description": (
                    "Self-contained prompt for the peer. Include any "
                    "context the peer needs — it does not see this "
                    "session's history. Max 4 KB."
                ),
            },
            "timeout": {
                "type": "number",
                "description": (
                    "Optional override of the call timeout in seconds (default 120, max 600)."
                ),
                "minimum": 1,
                "maximum": 600,
            },
        },
        "required": ["bot", "message"],
    },
}

ALL_TOOLS: list[dict[str, Any]] = [CALL_BOT_TOOL]


# ─── JSON-RPC helpers ─────────────────────────────────────────────────────


def _read_message(stream) -> dict[str, Any] | None:
    line = stream.readline()
    if not line:
        return None
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError as exc:
        logger.warning("invalid JSON-RPC line: %s (%s)", line, exc)
        return None


def _write_message(stream, message: dict[str, Any]) -> None:
    stream.write(json.dumps(message, ensure_ascii=False) + "\n")
    stream.flush()


def _result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _text_result(text: str, *, is_error: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "content": [{"type": "text", "text": text}],
        "_meta": dict(RESULT_META),
    }
    if is_error:
        payload["isError"] = True
    return payload


# ─── caller resolution ────────────────────────────────────────────────────


def _resolve_caller_bot_name() -> str | None:
    """Walk parents of cwd until grandparent is ``bots/``.

    Same heuristic as ``conversation_search`` / ``recall_fact`` so DM /
    cron / heartbeat working dirs all resolve to a single bot name.
    """
    cwd = Path.cwd().resolve()
    for ancestor in [cwd, *cwd.parents]:
        if ancestor.parent.name == "bots":
            return ancestor.name
    return None


# ─── depth tracking ───────────────────────────────────────────────────────


def _current_depth() -> int:
    raw = os.environ.get(DEPTH_ENV, "0")
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


# ─── call_bot implementation ──────────────────────────────────────────────


def _call_bot(args: dict[str, Any]) -> dict[str, Any]:
    """Invoke the peer bot's LLM and return the reply text."""
    caller = _resolve_caller_bot_name()
    if caller is None:
        return _text_result(
            "could not resolve caller bot from cwd; expected ancestor under bots/",
            is_error=True,
        )

    peer = str(args.get("bot", "")).strip()
    message = str(args.get("message", ""))
    if not peer:
        return _text_result("bot is required", is_error=True)
    if peer == caller:
        return _text_result(
            "self-call rejected — call_bot is for cross-bot delegation",
            is_error=True,
        )
    encoded = message.encode("utf-8")
    if not encoded.strip():
        return _text_result("message is required", is_error=True)
    if len(encoded) > MAX_MESSAGE_BYTES:
        return _text_result(
            f"message too long ({len(encoded)} > {MAX_MESSAGE_BYTES} bytes)",
            is_error=True,
        )

    current_depth = _current_depth()
    if current_depth >= MAX_DEPTH:
        return _text_result(
            f"call_bot depth cap reached ({current_depth} >= {MAX_DEPTH}); refusing",
            is_error=True,
        )

    timeout_raw = args.get("timeout")
    try:
        timeout = float(timeout_raw) if timeout_raw is not None else DEFAULT_TIMEOUT_SECONDS
    except (TypeError, ValueError):
        return _text_result("timeout must be a number", is_error=True)
    timeout = max(1.0, min(timeout, 600.0))

    # Lazy imports — these pull in the Claude Code backend, which
    # itself spawns subprocesses. Importing them at module top-time
    # would slow every MCP tools/list call.
    from abyss.config import bot_directory, load_bot_config
    from abyss.llm.base import LLMRequest
    from abyss.llm.registry import get_or_create

    peer_config = load_bot_config(peer)
    if peer_config is None:
        return _text_result(f"peer bot not found: {peer}", is_error=True)

    session_label = f"peer_call:{caller}:{peer}:{current_depth + 1}"
    session_dir = bot_directory(peer) / "peer_call_sessions" / f"from_{caller}"
    session_dir.mkdir(parents=True, exist_ok=True)

    # Bump the depth env for any tools the peer itself spawns. The
    # peer's own MCP servers inherit env via Claude Code spawn, so
    # this counter survives the recursion.
    new_depth_env = str(current_depth + 1)
    os.environ[DEPTH_ENV] = new_depth_env
    try:
        backend = get_or_create(peer, peer_config)
        request = LLMRequest(
            bot_name=peer,
            bot_path=bot_directory(peer),
            session_directory=session_dir,
            working_directory=str(session_dir),
            bot_config=peer_config,
            user_prompt=message,
            timeout=int(timeout),
            session_key=session_label,
        )
        logger.info(
            "call_bot caller=%s peer=%s depth=%d → %d",
            caller,
            peer,
            current_depth,
            current_depth + 1,
        )
        result = asyncio.run(_run_with_timeout(backend.run(request), timeout))
    except TimeoutError:
        return _text_result(f"call_bot timed out after {timeout:.0f}s", is_error=True)
    except Exception as exc:  # noqa: BLE001
        logger.exception("call_bot failed: %s", exc)
        return _text_result(f"call_bot internal error: {exc}", is_error=True)
    finally:
        # Restore the caller-side depth env so unrelated sibling
        # tools don't see an inflated counter.
        if current_depth == 0:
            os.environ.pop(DEPTH_ENV, None)
        else:
            os.environ[DEPTH_ENV] = str(current_depth)

    reply_text = (result.text or "").strip()
    if not reply_text:
        return _text_result(f"(peer '{peer}' returned an empty reply)", is_error=True)
    return _text_result(reply_text)


async def _run_with_timeout(coro, timeout: float):
    """Wrap ``coro`` in ``asyncio.wait_for`` and convert TimeoutError."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise TimeoutError(str(exc)) from exc


_TOOL_DISPATCH = {"call_bot": _call_bot}


# ─── handlers ─────────────────────────────────────────────────────────────


def _handle_initialize(request_id: Any) -> dict[str, Any]:
    return _result(
        request_id,
        {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        },
    )


def _handle_tools_list(request_id: Any) -> dict[str, Any]:
    return _result(request_id, {"tools": ALL_TOOLS})


def _handle_tools_call(request_id: Any, params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    args = params.get("arguments") or {}
    handler = _TOOL_DISPATCH.get(name)
    if handler is None:
        return _error(request_id, -32601, f"unknown tool: {name}")
    try:
        result = handler(args)
    except Exception as exc:  # noqa: BLE001
        logger.exception("call_bot MCP tool %s failed", name)
        result = _text_result(f"internal error: {exc}", is_error=True)
    return _result(request_id, result)


# ─── main loop ────────────────────────────────────────────────────────────


def serve(stdin=None, stdout=None) -> None:
    """Read JSON-RPC requests on stdin and reply on stdout until EOF."""
    if stdin is None:
        stdin = sys.stdin
    if stdout is None:
        stdout = sys.stdout

    while True:
        msg = _read_message(stdin)
        if msg is None:
            return

        method = msg.get("method")
        request_id = msg.get("id")
        params = msg.get("params") or {}

        if request_id is None:
            continue

        try:
            if method == "initialize":
                response = _handle_initialize(request_id)
            elif method == "tools/list":
                response = _handle_tools_list(request_id)
            elif method == "tools/call":
                response = _handle_tools_call(request_id, params)
            elif method == "ping":
                response = _result(request_id, {})
            else:
                response = _error(request_id, -32601, f"method not found: {method}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("MCP handler error for method %s", method)
            response = _error(request_id, -32603, f"internal error: {exc}")

        _write_message(stdout, response)


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("ABYSS_MCP_LOG_LEVEL", "WARNING"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    serve()


if __name__ == "__main__":
    main()
