"""MCP stdio server — bot reports goal progress to ``goals.yaml``.

Phase 6 of the co-evolution roadmap. One tool — ``record_progress``.

The bot decides when something it just finished counts as progress on
an existing goal. The human curates the goal list itself via dashboard
or CLI (so the bot can't invent new goals — that would be noise);
``record_progress`` only appends to an existing goal's timeline.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "abyss-record-progress"
SERVER_VERSION = "1.0.0"

MAX_RESULT_SIZE_CHARS = 200_000
RESULT_META: dict[str, Any] = {"anthropic/maxResultSizeChars": MAX_RESULT_SIZE_CHARS}

MAX_NOTE_BYTES = 2048


# ─── tool definition ──────────────────────────────────────────────────────


RECORD_PROGRESS_TOOL: dict[str, Any] = {
    "name": "record_progress",
    "description": (
        "Log one progress entry on an existing goal in your "
        "``goals.yaml``. Use this when you just did something that "
        "moves a goal forward — e.g. you closed a PR for the "
        "'ship-blog' goal, or you talked to 5 users for the "
        "'customer-discovery' goal. The note should be one sentence "
        "describing what advanced. ``value`` is optional and only "
        "meaningful for quantitative goals (e.g. MRR delta). You "
        "cannot invent new goals here — only append to ones the "
        "human already defined."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "goal_id": {
                "type": "string",
                "description": (
                    "Slug id of the existing goal (see goals.yaml). "
                    "Call list_goals via the dashboard / CLI to discover."
                ),
            },
            "note": {
                "type": "string",
                "description": "One sentence describing the progress. Max 2 KB.",
            },
            "value": {
                "type": "number",
                "description": (
                    "Optional numeric delta for quantitative goals "
                    "(e.g. MRR added, signups gained)."
                ),
            },
        },
        "required": ["goal_id", "note"],
    },
}

ALL_TOOLS: list[dict[str, Any]] = [RECORD_PROGRESS_TOOL]


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


def _resolve_bot_name() -> str | None:
    cwd = Path.cwd().resolve()
    for ancestor in [cwd, *cwd.parents]:
        if ancestor.parent.name == "bots":
            return ancestor.name
    return None


# ─── tool implementation ──────────────────────────────────────────────────


def _call_record_progress(args: dict[str, Any]) -> dict[str, Any]:
    from abyss.goals import get_goal, record_progress

    bot = _resolve_bot_name()
    if bot is None:
        return _text_result(
            "could not resolve bot from cwd; expected ancestor under bots/",
            is_error=True,
        )

    goal_id = str(args.get("goal_id", "")).strip()
    note = str(args.get("note", ""))
    value_raw = args.get("value")
    if not goal_id:
        return _text_result("goal_id is required", is_error=True)
    if not note.strip():
        return _text_result("note is required", is_error=True)
    if len(note.encode("utf-8")) > MAX_NOTE_BYTES:
        return _text_result(f"note too long (>{MAX_NOTE_BYTES} bytes)", is_error=True)

    value: float | None = None
    if value_raw is not None:
        try:
            value = float(value_raw)
        except (TypeError, ValueError):
            return _text_result("value must be a number", is_error=True)

    if get_goal(bot, goal_id) is None:
        return _text_result(
            f"goal not found for {bot}: {goal_id!r} — "
            "ask the human to add it first via the dashboard.",
            is_error=True,
        )
    entry = record_progress(bot, goal_id, note, value=value)
    if entry is None:
        # Should be unreachable given the existence check above, but
        # keep a defensive branch so a race doesn't crash the server.
        return _text_result(f"failed to append progress for {goal_id!r}", is_error=True)
    return _text_result(
        json.dumps(
            {
                "bot": bot,
                "goal_id": goal_id,
                "ts": entry.ts,
                "note": entry.note,
                **({"value": entry.value} if entry.value is not None else {}),
            },
            ensure_ascii=False,
        )
    )


_TOOL_DISPATCH = {"record_progress": _call_record_progress}


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
        logger.exception("record_progress MCP tool %s failed", name)
        result = _text_result(f"internal error: {exc}", is_error=True)
    return _result(request_id, result)


# ─── main loop ────────────────────────────────────────────────────────────


def serve(stdin=None, stdout=None) -> None:
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
