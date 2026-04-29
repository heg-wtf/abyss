"""PreCompact hook entry point.

Claude Code 2.1.105 fires this script when it is about to compact a
session's context window. abyss reuses the signal to also compact its
bot-level persistent files (MEMORY.md, HEARTBEAT.md, user SKILL.md):
the moment Claude Code itself decides the conversation is heavy enough
to warrant transcript compaction is a natural moment to also collapse
the bot's long-lived markdown.

Safety
------
The script aborts with exit 0 unless ``AI_AGENT == "abyss"``. This
means a stray entry in the user's global ``~/.claude/settings.json``
cannot fire abyss compaction for non-abyss sessions, even though the
hook command would still be invoked by Claude Code: abyss subprocesses
inject ``AI_AGENT=abyss`` (Phase 1), and nothing else does.

The hook never blocks. Even on internal error it returns exit 0 — the
existing cron / heartbeat fallback path keeps compacting on its own
schedule, so a hook failure is not load-bearing.

Run as ``python -m abyss.hooks.precompact_hook``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("abyss.hooks.precompact")

EXIT_OK = 0


def _resolve_bot_name_from_cwd(cwd: str) -> str | None:
    """Walk parents of ``cwd`` until one whose parent is named ``bots``.

    Mirrors ``claude_runner._resolve_bot_dir_from_working_directory`` so
    DM sessions (``bots/<name>/sessions/chat_*/``), cron sessions
    (``bots/<name>/cron_sessions/<job>/``) and heartbeat sessions
    (``bots/<name>/heartbeat_sessions/``) all resolve to the same bot.
    Returns ``None`` when no ``bots/<name>/`` ancestor exists.
    """
    path = Path(cwd).resolve()
    for candidate in [path, *path.parents]:
        if candidate.parent.name == "bots":
            return candidate.name
    return None


def _read_payload(stream: Any) -> dict[str, Any]:
    """Read Claude Code's JSON hook payload, tolerating malformed input."""
    try:
        text = stream.read()
    except Exception:  # noqa: BLE001
        return {}
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("PreCompact hook received non-JSON payload; skipping compact")
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def _run_compact(bot_name: str) -> None:
    """Invoke abyss token_compact for ``bot_name`` and persist results."""
    # Local import keeps the hook startup time minimal when guard rejects.
    from abyss.token_compact import run_compact, save_compact_results

    results = await run_compact(bot_name)
    save_compact_results(results)
    logger.info(
        "PreCompact hook: compacted %d target(s) for bot %s",
        len(results),
        bot_name,
    )


def main(stdin: Any | None = None) -> int:
    """Entry point. Always returns 0; never blocks the host compact."""
    if os.environ.get("AI_AGENT") != "abyss":
        # Not an abyss subprocess — silently no-op so the host's compact
        # proceeds unaltered.
        return EXIT_OK

    payload = _read_payload(stdin if stdin is not None else sys.stdin)
    cwd = payload.get("cwd")
    if not cwd:
        # Empty stdin, malformed JSON, non-object payload, or a real
        # PreCompact run that omits ``cwd`` all land here. Do NOT fall
        # back to ``os.getcwd()``: the hook subprocess inherits the bot
        # session directory from its parent, so a fallback would let an
        # invalid payload still trigger compaction. Skip instead.
        logger.info("PreCompact hook: payload missing cwd; skipping")
        return EXIT_OK

    bot_name = _resolve_bot_name_from_cwd(cwd)
    if bot_name is None:
        logger.info(
            "PreCompact hook: cwd %s not under bots/<name>/; skipping",
            cwd,
        )
        return EXIT_OK

    try:
        asyncio.run(_run_compact(bot_name))
    except Exception:  # noqa: BLE001
        logger.exception("PreCompact hook failed for bot %s", bot_name)

    return EXIT_OK


if __name__ == "__main__":
    logging.basicConfig(
        level=os.environ.get("ABYSS_HOOK_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    sys.exit(main())
