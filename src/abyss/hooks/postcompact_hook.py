"""PostCompact hook — measure persona drift after Claude Code compacts.

Claude Code 2.1.121+ fires this hook AFTER it finishes compacting the
session's context window. abyss reuses the signal to take a
``persona_drift`` snapshot tagged ``event="post-compact"`` and compare
it against the most recent snapshot before the compact ran. If the
composed CLAUDE.md shrank past the threshold (default 10% of total
bytes), we log a warning + fire a best-effort Web Push so the human
notices before the bot's tone drifts further.

The hook never blocks: any internal error returns exit 0 so a misfire
cannot break the host session.

Run as ``python -m abyss.hooks.postcompact_hook``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("abyss.hooks.postcompact")

EXIT_OK = 0


def _resolve_bot_name_from_cwd(cwd: str) -> str | None:
    """Walk parents of ``cwd`` until grandparent is ``bots/``."""
    path = Path(cwd).resolve()
    for candidate in [path, *path.parents]:
        if candidate.parent.name == "bots":
            return candidate.name
    return None


def _payload_from_stdin() -> dict:
    """Best-effort parse of the Claude Code hook payload."""
    if sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def main() -> int:
    if os.environ.get("AI_AGENT") != "abyss":
        # Guard: a stray entry in ~/.claude/settings.json could fire
        # this for non-abyss sessions, which would compose the wrong
        # CLAUDE.md. Be the inverse of an honest guest.
        return EXIT_OK

    payload = _payload_from_stdin()
    cwd = payload.get("cwd") or os.environ.get("PWD") or os.getcwd()
    bot_name = _resolve_bot_name_from_cwd(cwd)
    if bot_name is None:
        return EXIT_OK

    try:
        from abyss.persona_drift import (
            compare_snapshots,
            iter_snapshots,
            shrinkage_threshold_pct,
            take_snapshot,
        )

        # Pull the most recent existing snapshot BEFORE we take the
        # post-compact one — that's our baseline for the drift call.
        prior = next(iter_snapshots(bot_name, limit=1), None)
        post = take_snapshot(bot_name, event="post-compact")
        if prior is None:
            # First-ever snapshot: nothing to compare against, just
            # record and move on.
            return EXIT_OK

        report = compare_snapshots(prior, post)
        if report.shrinkage_alert:
            logger.warning(
                "PostCompact persona drift: bot=%s shrinkage=%.1f%% baseline=%d → %d",
                bot_name,
                report.total_delta_pct * 100,
                report.baseline_bytes,
                report.latest_bytes,
            )
            try:
                from abyss.web_push import send_push

                asyncio.run(
                    send_push(
                        title=f"🧬 {bot_name} persona drift",
                        body=(
                            f"CLAUDE.md shrank {abs(report.total_delta_pct) * 100:.0f}% "
                            f"after compact (threshold {shrinkage_threshold_pct() * 100:.0f}%)."
                        ),
                        bot=bot_name,
                        kind="persona_drift",
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("postcompact_hook push notify skipped: %s", exc)
    except Exception as exc:  # noqa: BLE001
        # Hook must never block — log and bail.
        logger.warning("postcompact_hook: unexpected failure: %s", exc)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
