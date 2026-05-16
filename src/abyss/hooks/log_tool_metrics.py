"""PostToolUse hook entry point — record per-tool execution metrics.

Claude Code 2.1.119 added ``duration_ms`` to PostToolUse hook payloads.
This script reads the JSON payload from stdin, resolves the bot from
``cwd``, and appends one event to the bot's
``tool_metrics/<YYMMDD>.jsonl`` via :mod:`abyss.tool_metrics`.

Same safety contract as the PreCompact hook (Phase 3):

- Aborts with exit 0 unless ``AI_AGENT == 'abyss'``.
- Never blocks: empty stdin, malformed JSON, missing payload fields,
  unresolvable bot dir, and any internal exception all return exit 0.

Run as ``python -m abyss.hooks.log_tool_metrics``.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("abyss.hooks.log_tool_metrics")

EXIT_OK = 0


def _resolve_bot_name_from_cwd(cwd: str) -> str | None:
    path = Path(cwd).resolve()
    for candidate in [path, *path.parents]:
        if candidate.parent.name == "bots":
            return candidate.name
    return None


def _read_payload(stream: Any) -> dict[str, Any]:
    try:
        text = stream.read()
    except Exception:  # noqa: BLE001
        return {}
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_duration_ms(payload: dict[str, Any]) -> float | None:
    """PostToolUse payloads expose duration at the top level (CC ≥ 2.1.119)."""
    raw = payload.get("duration_ms")
    if raw is None:
        # Some Claude Code releases nest it under tool_response.
        response = payload.get("tool_response")
        if isinstance(response, dict):
            raw = response.get("duration_ms")
    if raw is None:
        return None
    try:
        return float(raw)
    except TypeError, ValueError:
        return None


def main(stdin: Any | None = None) -> int:
    if os.environ.get("AI_AGENT") != "abyss":
        return EXIT_OK

    payload = _read_payload(stdin if stdin is not None else sys.stdin)
    cwd = payload.get("cwd")
    if not cwd:
        return EXIT_OK

    bot_name = _resolve_bot_name_from_cwd(cwd)
    if bot_name is None:
        return EXIT_OK

    tool = payload.get("tool_name") or payload.get("tool")
    duration_ms = _extract_duration_ms(payload)
    if not tool or duration_ms is None:
        return EXIT_OK

    exit_code: int | None = None
    response = payload.get("tool_response")
    if isinstance(response, dict):
        raw_exit = response.get("exit_code")
        if isinstance(raw_exit, (int, float)):
            exit_code = int(raw_exit)

    session_id = payload.get("session_id")

    # The PostToolUse vs PostToolUseFailure channel is selected by the
    # settings.json hook entry — we receive that distinction via
    # ``ABYSS_HOOK_OUTCOME`` (set in the hook command line). Default to
    # success so legacy / standalone invocations still record sensibly.
    outcome = os.environ.get("ABYSS_HOOK_OUTCOME") or "success"
    if outcome not in ("success", "failure"):
        outcome = "success"

    try:
        from abyss.tool_metrics import append_event

        append_event(
            bot_name,
            tool=str(tool),
            duration_ms=duration_ms,
            exit_code=exit_code,
            session_id=session_id if isinstance(session_id, str) else None,
            extra={"outcome": outcome},
        )
    except Exception:  # noqa: BLE001
        logger.exception("log_tool_metrics hook failed for bot %s", bot_name)

    return EXIT_OK


if __name__ == "__main__":
    logging.basicConfig(
        level=os.environ.get("ABYSS_HOOK_LOG_LEVEL", "WARNING"),
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    sys.exit(main())
