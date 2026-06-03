"""MCP stdio server letting bots propose a GitHub skill for human review.

Phase 5 of the co-evolution roadmap. One tool only — ``propose_skill``.

The server resolves the bot from cwd (walk parents until grandparent
is ``bots/``), validates the URL is a GitHub repo, adds the proposal
to ``bots/<name>/skill_proposals.yaml`` (with dedup against pending /
approved / rejected entries), and fires a best-effort Web Push so the
human notices something landed in the queue.
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
SERVER_NAME = "abyss-propose-skill"
SERVER_VERSION = "1.0.0"

MAX_RESULT_SIZE_CHARS = 200_000
RESULT_META: dict[str, Any] = {"anthropic/maxResultSizeChars": MAX_RESULT_SIZE_CHARS}


# ─── tool definition ──────────────────────────────────────────────────────


PROPOSE_SKILL_TOOL: dict[str, Any] = {
    "name": "propose_skill",
    "description": (
        "Suggest a GitHub skill the bot would like to gain. Use this "
        "when you tried to fulfil a request and noticed a missing "
        "capability — e.g. you needed to read a Stripe invoice but "
        "have no Stripe tool. The proposal lands in a queue the human "
        "reviews; they approve or reject. Do not call repeatedly for "
        "the same URL — the store dedups, and a rejected URL stays "
        "rejected (do not re-propose). Provide a short concrete "
        "reason that names the missing capability and the situation "
        "that exposed it."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "candidate_url": {
                "type": "string",
                "description": (
                    "GitHub repo URL of the proposed skill. Must start with https://github.com/."
                ),
            },
            "reason": {
                "type": "string",
                "description": (
                    "One sentence: what capability is missing and which situation exposed it."
                ),
            },
            "alternative_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional alternative GitHub URLs the human can "
                    "consider instead of the primary candidate."
                ),
            },
        },
        "required": ["candidate_url", "reason"],
    },
}

ALL_TOOLS: list[dict[str, Any]] = [PROPOSE_SKILL_TOOL]


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
    cwd = Path.cwd().resolve()
    for ancestor in [cwd, *cwd.parents]:
        if ancestor.parent.name == "bots":
            return ancestor.name
    return None


# ─── tool implementation ──────────────────────────────────────────────────


_VALID_PREFIXES = ("https://github.com/",)


def _looks_like_github_repo(url: str) -> bool:
    if not isinstance(url, str):
        return False
    if not url.startswith(_VALID_PREFIXES):
        return False
    # https://github.com/owner/repo[/...] — owner and repo non-empty
    tail = url[len("https://github.com/") :]
    parts = [segment for segment in tail.split("/") if segment]
    return len(parts) >= 2


def _maybe_notify(bot: str, reason: str) -> None:
    """Fire a Web Push, swallowing any error."""
    try:
        from abyss.web_push import send_push
    except Exception:  # noqa: BLE001
        return
    body = (reason or "").strip()
    if len(body) > 120:
        body = body[:117] + "…"
    try:
        asyncio.run(
            send_push(
                title=f"💡 {bot} 새 skill 제안",
                body=body or "(no reason given)",
                bot=bot,
                kind="skill_proposal",
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("propose_skill push notify skipped: %s", exc)


def _call_propose_skill(args: dict[str, Any]) -> dict[str, Any]:
    from abyss.skill_proposals import add_proposal

    bot = _resolve_bot_name()
    if bot is None:
        return _text_result(
            "could not resolve bot from cwd; expected ancestor under bots/",
            is_error=True,
        )
    candidate_url = str(args.get("candidate_url", "")).strip()
    reason = str(args.get("reason", "")).strip()
    alternative_urls = args.get("alternative_urls") or []
    if not isinstance(alternative_urls, list):
        return _text_result("alternative_urls must be a list", is_error=True)
    alts = [str(url).strip() for url in alternative_urls if str(url).strip()]
    if not candidate_url or not reason:
        return _text_result("candidate_url and reason are required", is_error=True)
    if not _looks_like_github_repo(candidate_url):
        return _text_result(
            "candidate_url must be a https://github.com/<owner>/<repo> URL",
            is_error=True,
        )
    for url in alts:
        if not _looks_like_github_repo(url):
            return _text_result(
                f"alternative_url is not a GitHub repo: {url}",
                is_error=True,
            )

    proposal = add_proposal(bot, candidate_url, reason, alternative_urls=alts)
    _maybe_notify(bot, reason)
    return _text_result(
        json.dumps(
            {
                "bot": bot,
                "proposal_id": proposal.id,
                "status": proposal.status,
                "candidate_url": proposal.candidate_url,
            },
            ensure_ascii=False,
        )
    )


_TOOL_DISPATCH = {"propose_skill": _call_propose_skill}


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
        logger.exception("propose_skill MCP tool %s failed", name)
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
