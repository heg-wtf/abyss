"""MCP stdio server exposing ABOUT_ME to Claude.

Phase 2b of the co-evolution roadmap (docs/plan-coevolution-2026-05-19.md).

Run as ``python -m abyss.mcp_servers.about_me`` (typically spawned by
Claude Code or the SDK). The server resolves ``~/.abyss/ABOUT_ME``
from the standard ``ABYSS_HOME`` env var that abyss already populates
for every Claude Code invocation.

Tools exposed:

- ``about_me_list_categories`` — enumerate categories + counts
- ``about_me_get`` — return confirmed + propose entries for one category
- ``about_me_search`` — substring search across all entries
- ``about_me_propose`` — add a propose entry (auto-confirms on 2nd time,
  detects conflicts vs confirmed entries)

The wire protocol is JSON-RPC 2.0 with newline-delimited messages, per
the Model Context Protocol stdio spec.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "abyss-about-me"
SERVER_VERSION = "1.0.0"

MAX_RESULT_SIZE_CHARS = 200_000
RESULT_META: dict[str, Any] = {"anthropic/maxResultSizeChars": MAX_RESULT_SIZE_CHARS}


# ─── tool definitions ─────────────────────────────────────────────────────


PROPOSE_TOOL: dict[str, Any] = {
    "name": "about_me_propose",
    "description": (
        "Propose a new fact about the user (ash84). When the same key + "
        "value is proposed twice, abyss auto-confirms it. When the value "
        "conflicts with an existing confirmed entry, the propose is "
        "queued with a conflict flag so the user can resolve it. Use "
        "kebab-case keys ('wife-name', 'morning-routine')."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": (
                    "One of: identity, relationships, preferences, "
                    "routines, current_focus, health, values."
                ),
            },
            "key": {
                "type": "string",
                "description": "Stable kebab-case identifier within the category.",
            },
            "value": {
                "type": "string",
                "description": "Concise fact (< 80 chars recommended).",
            },
            "body": {
                "type": "string",
                "description": "Optional longer markdown explanation.",
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "How sure you are. Default 'medium' for new claims.",
                "default": "medium",
            },
        },
        "required": ["category", "key", "value"],
    },
}

GET_TOOL: dict[str, Any] = {
    "name": "about_me_get",
    "description": (
        "Return every entry (confirmed + propose) for a category. Use "
        "this when the INDEX summary is not detailed enough."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "Category name.",
            }
        },
        "required": ["category"],
    },
}

LIST_TOOL: dict[str, Any] = {
    "name": "about_me_list_categories",
    "description": "List every category with per-status counts.",
    "inputSchema": {"type": "object", "properties": {}, "required": []},
}

SEARCH_TOOL: dict[str, Any] = {
    "name": "about_me_search",
    "description": (
        "Case-insensitive substring search across every ABOUT_ME entry. "
        "Returns matching entries with their category."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Substring to find in key/value/body.",
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
    },
}

ALL_TOOLS: list[dict[str, Any]] = [PROPOSE_TOOL, GET_TOOL, LIST_TOOL, SEARCH_TOOL]


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


def _serialize_entry(entry: Any, *, category: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "key": entry.key,
        "value": entry.value,
        "confidence": entry.confidence,
        "source": entry.source,
        "added": entry.added,
        "last_confirmed": entry.last_confirmed,
        "status": entry.status,
    }
    if entry.body:
        payload["body"] = entry.body
    if entry.extra:
        for key, value in entry.extra.items():
            payload.setdefault(key, value)
    if category is not None:
        payload["category"] = category
    return payload


def _call_propose(args: dict[str, Any]) -> dict[str, Any]:
    from abyss.about_me import propose_entry

    category = str(args.get("category") or "").strip()
    key = str(args.get("key") or "").strip()
    value = str(args.get("value") or "").strip()
    body = str(args.get("body") or "").strip()
    confidence = str(args.get("confidence") or "medium")

    if not category or not key or not value:
        return _text_result(
            "category, key, and value are all required for about_me_propose.",
            is_error=True,
        )

    try:
        result = propose_entry(
            category=category,
            key=key,
            value=value,
            body=body,
            confidence=confidence,
        )
    except ValueError as exc:
        return _text_result(str(exc), is_error=True)

    payload = {
        "action": result.action,
        "category": result.category,
        "key": result.key,
        "propose_count": result.propose_count,
    }
    if result.conflict_with:
        payload["conflicts_with"] = result.conflict_with

    return {
        "content": [
            {"type": "text", "text": json.dumps(payload, ensure_ascii=False)},
        ],
        "_meta": dict(RESULT_META),
    }


def _call_get(args: dict[str, Any]) -> dict[str, Any]:
    from abyss.about_me import load_category

    category = str(args.get("category") or "").strip()
    if not category:
        return _text_result("category required.", is_error=True)
    try:
        entries = load_category(category)
    except ValueError as exc:
        return _text_result(str(exc), is_error=True)
    payload = {
        "category": category,
        "entries": [_serialize_entry(entry) for entry in entries],
    }
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "_meta": dict(RESULT_META),
    }


def _call_list_categories(_args: dict[str, Any]) -> dict[str, Any]:
    from abyss.about_me import category_counts

    counts = category_counts()
    return {
        "content": [
            {"type": "text", "text": json.dumps(counts, ensure_ascii=False)},
        ],
        "_meta": dict(RESULT_META),
    }


def _call_search(args: dict[str, Any]) -> dict[str, Any]:
    from abyss.about_me import ABOUT_ME_CATEGORIES, load_category

    query = str(args.get("query") or "").strip()
    if not query:
        return _text_result("query required.", is_error=True)
    needle = query.lower()
    limit_raw = args.get("limit", 20)
    try:
        limit = max(1, min(100, int(limit_raw)))
    except (TypeError, ValueError):
        limit = 20

    hits: list[dict[str, Any]] = []
    for category in ABOUT_ME_CATEGORIES:
        for entry in load_category(category):
            haystack = " ".join(
                [
                    entry.key,
                    entry.value,
                    entry.body,
                ]
            ).lower()
            if needle in haystack:
                hits.append(_serialize_entry(entry, category=category))
                if len(hits) >= limit:
                    break
        if len(hits) >= limit:
            break

    payload = {"query": query, "count": len(hits), "hits": hits}
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "_meta": dict(RESULT_META),
    }


_TOOL_DISPATCH = {
    PROPOSE_TOOL["name"]: _call_propose,
    GET_TOOL["name"]: _call_get,
    LIST_TOOL["name"]: _call_list_categories,
    SEARCH_TOOL["name"]: _call_search,
}


def _handle_tools_call(request_id: Any, params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    args = params.get("arguments") or {}
    handler = _TOOL_DISPATCH.get(name)
    if handler is None:
        return _error(request_id, -32601, f"unknown tool: {name}")
    try:
        result = handler(args)
    except Exception as exc:  # noqa: BLE001
        logger.exception("about_me MCP tool %s failed", name)
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
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    serve()


if __name__ == "__main__":
    main()
