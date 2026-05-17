"""MCP stdio server exposing conversation search to Claude.

Run as ``python -m abyss.mcp_servers.conversation_search`` (typically
spawned by Claude Code or the SDK). The server reads the DB path from
the ``ABYSS_CONVERSATION_DB`` environment variable, which abyss
populates when composing each bot's MCP configuration.

The wire protocol is JSON-RPC 2.0 with newline-delimited messages, per
the Model Context Protocol stdio spec.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from abyss import conversation_index

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "abyss-conversation-search"
SERVER_VERSION = "1.0.0"

# Tool result persistence ceiling, per Claude Code 2.1.91 changelog.
# ``_meta["anthropic/maxResultSizeChars"]`` lets large search payloads
# survive transcript persistence without truncation (default ceiling
# would otherwise force the host to drop characters from the result).
# 500_000 is the documented upper bound.
MAX_RESULT_SIZE_CHARS = 500_000
RESULT_META: dict[str, Any] = {"anthropic/maxResultSizeChars": MAX_RESULT_SIZE_CHARS}

TOOL_NAME = "search_conversations"
TOOL_DESCRIPTION = (
    "Full-text search over the bot's past conversations (BM25 ranking). "
    "Use this to recall specific facts, names, dates, or topics that the "
    "user mentioned earlier and that aren't in your current context. "
    "Markdown logs are the source of truth; this tool searches an "
    "auto-maintained SQLite FTS5 index built from those logs."
)

TOOL_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Keywords to search for. Multiple words are AND-combined. "
                "Use specific nouns, names, or dates rather than generic verbs."
            ),
        },
        "since": {
            "type": "string",
            "description": "Inclusive lower bound, ISO date YYYY-MM-DD.",
        },
        "until": {
            "type": "string",
            "description": "Inclusive upper bound, ISO date YYYY-MM-DD.",
        },
        "chat_id": {
            "type": "string",
            "description": ("Restrict to a specific chat (e.g. 'chat_42'). Omit for all chats."),
        },
        "role": {
            "type": "string",
            "description": ("Restrict to 'user', 'assistant', or a group sender label."),
        },
        "limit": {
            "type": "integer",
            "description": "Maximum hits to return (default 20).",
            "default": 20,
            "minimum": 1,
            "maximum": 100,
        },
    },
    "required": ["query"],
}


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
    return _result(
        request_id,
        {
            "tools": [
                {
                    "name": TOOL_NAME,
                    "description": TOOL_DESCRIPTION,
                    "inputSchema": TOOL_INPUT_SCHEMA,
                }
            ]
        },
    )


def _handle_tools_call(
    request_id: Any, params: dict[str, Any], db_path: Path | None
) -> dict[str, Any]:
    name = params.get("name")
    args = params.get("arguments") or {}

    if name != TOOL_NAME:
        return _error(request_id, -32601, f"unknown tool: {name}")

    if db_path is None:
        return _result(
            request_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Conversation search is not configured for this bot "
                            "(ABYSS_CONVERSATION_DB env var missing)."
                        ),
                    }
                ],
                "isError": True,
                "_meta": dict(RESULT_META),
            },
        )

    query = args.get("query") or ""
    if not query.strip():
        return _result(
            request_id,
            {
                "content": [{"type": "text", "text": "Empty query — no search performed."}],
                "isError": True,
                "_meta": dict(RESULT_META),
            },
        )

    since = _parse_date(args.get("since"))
    until = _parse_date(args.get("until"))
    chat_id = args.get("chat_id")
    role = args.get("role")
    limit_raw = args.get("limit", 20)
    try:
        limit = max(1, min(100, int(limit_raw)))
    except (TypeError, ValueError):
        limit = 20

    hits = conversation_index.search(
        db_path,
        query=query,
        since=since,
        until=until,
        chat_id=chat_id,
        role=role,
        limit=limit,
    )

    return _result(
        request_id,
        {"content": _format_hits(hits, query), "_meta": dict(RESULT_META)},
    )


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d")
    except ValueError:
        return None


def _format_hits(hits: list, query: str) -> list[dict[str, Any]]:
    if not hits:
        return [
            {
                "type": "text",
                "text": f"No conversation messages matched query: {query!r}.",
            }
        ]

    lines = [f"Found {len(hits)} match(es) for {query!r}:", ""]
    for hit in hits:
        ts = hit.ts
        chat = hit.chat_id
        role = hit.role
        snippet = hit.snippet.replace("\n", " ")
        lines.append(f"- [{ts}] ({chat}, {role}) {snippet}")
    payload = "\n".join(lines)
    return [{"type": "text", "text": payload}]


# ─── main loop ────────────────────────────────────────────────────────────


def _resolve_db_path() -> Path | None:
    raw = os.environ.get("ABYSS_CONVERSATION_DB")
    if not raw:
        return None
    return Path(raw).expanduser()


def serve(stdin=None, stdout=None) -> None:
    """Read JSON-RPC requests on stdin and reply on stdout until EOF."""
    if stdin is None:
        stdin = sys.stdin
    if stdout is None:
        stdout = sys.stdout

    db_path = _resolve_db_path()

    while True:
        msg = _read_message(stdin)
        if msg is None:
            return

        method = msg.get("method")
        request_id = msg.get("id")
        params = msg.get("params") or {}

        # Notifications have no id and require no response.
        if request_id is None:
            continue

        try:
            if method == "initialize":
                response = _handle_initialize(request_id)
            elif method == "tools/list":
                response = _handle_tools_list(request_id)
            elif method == "tools/call":
                response = _handle_tools_call(request_id, params, db_path)
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
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    serve()


if __name__ == "__main__":
    main()
