"""Per-bot tool execution metrics.

Each PostToolUse hook fire appends one event to ``tool_metrics/<YYMMDD>.jsonl``
under the bot's runtime directory. The directory is rotated to keep at most
``RETENTION_DAYS`` of history. Files are plain JSONL so abysscope can stream
them directly without a database.

Schema (one event per line):

    {
      "ts": "2026-04-30T07:23:45+00:00",
      "tool": "Bash",
      "duration_ms": 423,
      "exit_code": 0,
      "session_id": "abc-123"
    }

``tool`` and ``duration_ms`` are mandatory; the rest is optional metadata
provided by Claude Code's PostToolUse payload.
"""

from __future__ import annotations

import json
import logging
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from abyss.config import bot_directory

logger = logging.getLogger(__name__)

METRICS_DIRNAME = "tool_metrics"
RETENTION_DAYS = 7
ROTATION_FILENAME_FMT = "%Y%m%d"
EVENT_TS_FMT = "%Y-%m-%dT%H:%M:%S%z"


def metrics_directory(bot_name: str) -> Path:
    """Return ``~/.abyss/bots/<name>/tool_metrics/``."""
    return bot_directory(bot_name) / METRICS_DIRNAME


def _today_path(bot_name: str, now: datetime | None = None) -> Path:
    when = now or datetime.now(timezone.utc)
    filename = when.strftime(ROTATION_FILENAME_FMT) + ".jsonl"
    return metrics_directory(bot_name) / filename


def _rotate(
    metrics_dir: Path,
    retention_days: int = RETENTION_DAYS,
    now: datetime | None = None,
) -> int:
    """Delete jsonl files older than ``retention_days``. Returns count removed."""
    reference = now or datetime.now(timezone.utc)
    cutoff_date = (reference - timedelta(days=retention_days)).date()
    removed = 0
    if not metrics_dir.exists():
        return 0
    for path in metrics_dir.glob("*.jsonl"):
        try:
            file_date = datetime.strptime(path.stem, ROTATION_FILENAME_FMT).date()
        except ValueError:
            # Unrelated file — leave it alone.
            continue
        if file_date < cutoff_date:
            with suppress(OSError):
                path.unlink()
                removed += 1
    return removed


def append_event(
    bot_name: str,
    tool: str,
    duration_ms: float,
    *,
    exit_code: int | None = None,
    session_id: str | None = None,
    extra: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> Path:
    """Append a single PostToolUse event and rotate stale files.

    Returns the jsonl path that was written. Best-effort: errors are
    logged and swallowed so a metrics failure cannot block tool execution.
    """
    if not tool:
        raise ValueError("tool name required")

    when = now or datetime.now(timezone.utc)
    record: dict[str, Any] = {
        "ts": when.strftime(EVENT_TS_FMT),
        "tool": tool,
        "duration_ms": float(duration_ms),
    }
    if exit_code is not None:
        record["exit_code"] = int(exit_code)
    if session_id:
        record["session_id"] = session_id
    if extra:
        # Defensive: only merge JSON-serialisable keys.
        for key, value in extra.items():
            if key in record:
                continue
            try:
                json.dumps(value)
            except (TypeError, ValueError):
                continue
            record[key] = value

    metrics_dir = metrics_directory(bot_name)
    metrics_dir.mkdir(parents=True, exist_ok=True)
    _rotate(metrics_dir, now=when)

    path = _today_path(bot_name, when)
    line = json.dumps(record, ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as file:
        file.write(line + "\n")
    return path


@dataclass
class ToolMetricsRow:
    tool: str
    count: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    error_count: int


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if pct <= 0:
        return sorted_values[0]
    if pct >= 100:
        return sorted_values[-1]
    rank = (pct / 100) * (len(sorted_values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = rank - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction


def iter_events(bot_name: str) -> Iterable[dict[str, Any]]:
    """Yield events from all jsonl files (oldest first)."""
    metrics_dir = metrics_directory(bot_name)
    if not metrics_dir.exists():
        return
    for path in sorted(metrics_dir.glob("*.jsonl")):
        try:
            with open(path, encoding="utf-8") as file:
                for line in file:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
        except OSError as error:
            logger.warning("tool_metrics: cannot read %s: %s", path, error)


def aggregate(bot_name: str) -> list[ToolMetricsRow]:
    """Return per-tool latency rows sorted by descending count.

    A call counts as an error when the recorded ``outcome`` is
    ``"failure"`` (set by the PostToolUseFailure channel) **or** when
    ``exit_code`` is non-zero. Either signal is enough — they're not
    always both present.
    """
    buckets: dict[str, list[float]] = {}
    errors: dict[str, int] = {}
    for event in iter_events(bot_name):
        tool = event.get("tool")
        duration = event.get("duration_ms")
        if not tool or duration is None:
            continue
        try:
            value = float(duration)
        except (TypeError, ValueError):
            continue
        buckets.setdefault(tool, []).append(value)

        is_failure = event.get("outcome") == "failure"
        exit_code = event.get("exit_code")
        if not is_failure and isinstance(exit_code, (int, float)) and exit_code != 0:
            is_failure = True
        if is_failure:
            errors[tool] = errors.get(tool, 0) + 1

    rows: list[ToolMetricsRow] = []
    for tool, values in buckets.items():
        rows.append(
            ToolMetricsRow(
                tool=tool,
                count=len(values),
                p50_ms=_percentile(values, 50),
                p95_ms=_percentile(values, 95),
                p99_ms=_percentile(values, 99),
                error_count=errors.get(tool, 0),
            )
        )
    rows.sort(key=lambda row: row.count, reverse=True)
    return rows
