"""Numeric feedback signal (1/2/3) storage and aggregation.

Phase 1 of the co-evolution roadmap (docs/plan-coevolution-2026-05-19.md).
Users rate assistant turns with a single tap: 1=good, 2=meh, 3=wrong.
Records land in ``~/.abyss/bots/<name>/feedback.jsonl`` as append-only JSONL,
and become the raw fuel for later phases (USER_MODEL, SELF.md, reflection
cron, DPO datasets).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from abyss.config import bot_directory

logger = logging.getLogger(__name__)

FEEDBACK_FILE_NAME = "feedback.jsonl"
VALID_SIGNALS = (1, 2, 3)
MAX_NOTE_LENGTH = 2000

SIGNAL_LABELS = {
    1: "good",
    2: "meh",
    3: "wrong",
}


def feedback_file(bot_name: str) -> Path:
    """Return the feedback jsonl path for a bot."""
    return bot_directory(bot_name) / FEEDBACK_FILE_NAME


def append_feedback(
    bot: str,
    session_id: str,
    turn_id: str,
    signal: int,
    note: str = "",
) -> dict[str, Any]:
    """Append a feedback record to ``feedback.jsonl`` and return it.

    Callers are responsible for input validation (signal range, note size,
    bot/session existence). This helper only writes.
    """
    record: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "bot": bot,
        "session_id": session_id,
        "turn_id": turn_id,
        "signal": int(signal),
        "note": note or "",
    }

    path = feedback_file(bot)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as file:
        file.write(line + "\n")

    return record


def load_feedback(bot: str) -> list[dict[str, Any]]:
    """Load every feedback record for a bot.

    Malformed lines are skipped with a warning log so a single corrupt entry
    does not break aggregation.
    """
    path = feedback_file(bot)
    if not path.exists():
        return []

    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as file:
        for line_number, raw in enumerate(file, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                records.append(json.loads(raw))
            except json.JSONDecodeError:
                logger.warning("skipping malformed feedback line %d in %s", line_number, path)
    return records


def aggregate(bot: str, last_n: int = 10) -> dict[str, Any]:
    """Aggregate feedback for a bot.

    Returns a dict with:
    - ``total``: total record count
    - ``count_by_signal``: ``{1: n1, 2: n2, 3: n3}``
    - ``latest_per_turn``: ``{turn_id: latest_record}`` (latest-wins)
    - ``last_entries``: most recent ``last_n`` records in chronological order
    """
    records = load_feedback(bot)

    count_by_signal = dict.fromkeys(VALID_SIGNALS, 0)
    latest_per_turn: dict[str, dict[str, Any]] = {}

    for record in records:
        signal = record.get("signal")
        if signal in count_by_signal:
            count_by_signal[signal] += 1
        turn_id = record.get("turn_id")
        if isinstance(turn_id, str) and turn_id:
            existing = latest_per_turn.get(turn_id)
            if existing is None or record.get("ts", "") >= existing.get("ts", ""):
                latest_per_turn[turn_id] = record

    return {
        "total": len(records),
        "count_by_signal": count_by_signal,
        "latest_per_turn": latest_per_turn,
        "last_entries": records[-last_n:],
    }
