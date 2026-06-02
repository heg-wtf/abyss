"""MCP stdio server exposing the Phase 4 episodic + fact stores to the bot.

Two read-only tools:

- ``recall_fact`` — query ``facts.db`` by subject / minimum confidence.
- ``recent_episodes`` — stream rows from ``episodes.jsonl`` newest-first.

The server is spawned per Claude Code invocation alongside the bot's
own working directory; the bot is resolved from ``cwd`` the same way
``conversation_search`` does (walk parents until the grandparent is
``bots/``). ``ABYSS_HOME`` is honoured for tests.

The wire protocol is JSON-RPC 2.0 with newline-delimited messages.
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
SERVER_NAME = "abyss-recall-fact"
SERVER_VERSION = "1.0.0"

MAX_RESULT_SIZE_CHARS = 200_000
RESULT_META: dict[str, Any] = {"anthropic/maxResultSizeChars": MAX_RESULT_SIZE_CHARS}


# ─── tool definitions ─────────────────────────────────────────────────────


RECALL_FACT_TOOL: dict[str, Any] = {
    "name": "recall_fact",
    "description": (
        "Look up structured facts the bot extracted in earlier sessions. "
        "Returns the highest-confidence rows for the requested subject "
        "or, if no subject is supplied, across all subjects."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "subject": {
                "type": "string",
                "description": "Short noun-phrase recall key. Optional.",
            },
            "k": {
                "type": "integer",
                "description": "Maximum rows to return (default 5).",
                "default": 5,
                "minimum": 1,
                "maximum": 50,
            },
            "min_confidence": {
                "type": "number",
                "description": "Drop rows below this confidence (default 0.5).",
                "default": 0.5,
                "minimum": 0.0,
                "maximum": 1.0,
            },
        },
    },
}

RECENT_EPISODES_TOOL: dict[str, Any] = {
    "name": "recent_episodes",
    "description": (
        "Stream the bot's episodic timeline newest-first. Useful when "
        "the bot needs context about what happened yesterday/last week."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": (
                    "Only include episodes whose date is within this many "
                    "days of today (default 7)."
                ),
                "default": 7,
                "minimum": 1,
                "maximum": 365,
            },
            "limit": {
                "type": "integer",
                "description": "Maximum rows to return (default 20).",
                "default": 20,
                "minimum": 1,
                "maximum": 200,
            },
            "kind": {
                "type": "string",
                "description": "Filter by kind: fact|event|decision|change.",
                "enum": ["fact", "event", "decision", "change"],
            },
        },
    },
}

ALL_TOOLS: list[dict[str, Any]] = [RECALL_FACT_TOOL, RECENT_EPISODES_TOOL]


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


# ─── bot resolution ───────────────────────────────────────────────────────


def _resolve_bot_name() -> str | None:
    """Walk parents of cwd until we find a directory whose parent is ``bots/``.

    Same heuristic as ``conversation_search`` so DM / cron / heartbeat
    working dirs all map back to the same bot. Returns ``None`` if no
    such ancestor is found — callers surface a clean error rather than
    silently querying the wrong bot.
    """
    cwd = Path.cwd().resolve()
    for ancestor in [cwd, *cwd.parents]:
        if ancestor.parent.name == "bots":
            return ancestor.name
    return None


# ─── tool implementations ─────────────────────────────────────────────────


def _call_recall_fact(args: dict[str, Any]) -> dict[str, Any]:
    from abyss.episodes import query_facts

    bot = _resolve_bot_name()
    if bot is None:
        return _text_result(
            "could not resolve bot from cwd; expected ancestor under bots/",
            is_error=True,
        )
    subject = args.get("subject")
    if subject is not None:
        subject = str(subject).strip() or None
    rows = query_facts(
        bot,
        subject=subject,
        min_confidence=float(args.get("min_confidence", 0.5)),
        limit=int(args.get("k", 5)),
    )
    if not rows:
        return _text_result("(no matching facts)")
    body = json.dumps({"bot": bot, "facts": rows}, ensure_ascii=False, default=str)
    return _text_result(body)


def _call_recent_episodes(args: dict[str, Any]) -> dict[str, Any]:
    from datetime import datetime, timedelta, timezone

    from abyss.episodes import iter_episodes

    bot = _resolve_bot_name()
    if bot is None:
        return _text_result(
            "could not resolve bot from cwd; expected ancestor under bots/",
            is_error=True,
        )
    days = int(args.get("days", 7))
    limit = int(args.get("limit", 20))
    kind = args.get("kind")
    since_dt = datetime.now(timezone.utc).date() - timedelta(days=days)
    since_iso = since_dt.isoformat()
    kinds = (str(kind),) if kind else None
    rows = list(iter_episodes(bot, since=since_iso, kinds=kinds, limit=limit))
    if not rows:
        return _text_result("(no recent episodes)")
    serialized = [
        {
            "date": row.date,
            "kind": row.kind,
            "summary": row.summary,
            "source_turn": row.source_turn,
        }
        for row in rows
    ]
    return _text_result(json.dumps({"bot": bot, "episodes": serialized}, ensure_ascii=False))


_TOOL_DISPATCH = {
    "recall_fact": _call_recall_fact,
    "recent_episodes": _call_recent_episodes,
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
        logger.exception("recall_fact MCP tool %s failed", name)
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
