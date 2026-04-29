"""Tests for ``abyss.tool_metrics``."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from abyss import tool_metrics


@pytest.fixture
def abyss_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / ".abyss"
    monkeypatch.setenv("ABYSS_HOME", str(home))
    return home


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_append_event_creates_file(abyss_home: Path) -> None:
    path = tool_metrics.append_event("alpha", "Bash", duration_ms=42.5)
    assert path.exists()
    rows = _read_jsonl(path)
    assert len(rows) == 1
    assert rows[0]["tool"] == "Bash"
    assert rows[0]["duration_ms"] == 42.5
    assert "ts" in rows[0]


def test_append_event_appends_multiple(abyss_home: Path) -> None:
    tool_metrics.append_event("alpha", "Bash", 10.0)
    tool_metrics.append_event("alpha", "Read", 20.0)
    path = tool_metrics._today_path("alpha")
    rows = _read_jsonl(path)
    assert {r["tool"] for r in rows} == {"Bash", "Read"}


def test_append_event_per_day_files(abyss_home: Path) -> None:
    """Different ``now`` values land in separate jsonl files."""
    today = datetime(2026, 4, 30, 10, 0, tzinfo=timezone.utc)
    yesterday = today - timedelta(days=1)
    tool_metrics.append_event("alpha", "Bash", 1.0, now=today)
    tool_metrics.append_event("alpha", "Bash", 2.0, now=yesterday)
    files = sorted((abyss_home / "bots" / "alpha" / "tool_metrics").glob("*.jsonl"))
    assert {p.name for p in files} == {"20260430.jsonl", "20260429.jsonl"}


def test_append_event_rotates_old_files(abyss_home: Path) -> None:
    """Files older than RETENTION_DAYS are deleted on append."""
    metrics_dir = tool_metrics.metrics_directory("alpha")
    metrics_dir.mkdir(parents=True)
    # Stale file (10 days old)
    (metrics_dir / "20260420.jsonl").write_text("stale\n")
    # Fresh file (today)
    today_value = datetime(2026, 4, 30, tzinfo=timezone.utc)
    tool_metrics.append_event("alpha", "Bash", 1.0, now=today_value)

    remaining = {p.name for p in metrics_dir.glob("*.jsonl")}
    assert "20260420.jsonl" not in remaining
    assert "20260430.jsonl" in remaining


def test_append_event_extra_metadata(abyss_home: Path) -> None:
    path = tool_metrics.append_event(
        "alpha",
        "Bash",
        100.0,
        exit_code=1,
        session_id="abc-123",
        extra={"matcher": "*", "pid": 999, "unserialisable": object()},
    )
    rows = _read_jsonl(path)
    assert rows[0]["exit_code"] == 1
    assert rows[0]["session_id"] == "abc-123"
    assert rows[0]["matcher"] == "*"
    assert rows[0]["pid"] == 999
    # Unserialisable values are dropped, not crashed on.
    assert "unserialisable" not in rows[0]


def test_append_event_rejects_empty_tool(abyss_home: Path) -> None:
    with pytest.raises(ValueError):
        tool_metrics.append_event("alpha", "", 1.0)


def test_aggregate_returns_p50_p95(abyss_home: Path) -> None:
    durations = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    for value in durations:
        tool_metrics.append_event("alpha", "Bash", value)

    rows = tool_metrics.aggregate("alpha")
    assert len(rows) == 1
    row = rows[0]
    assert row.tool == "Bash"
    assert row.count == 10
    assert row.p50_ms == pytest.approx(55.0)
    # 95th percentile of [10..100] step 10 with linear interp at index 8.55 -> 95.5
    assert row.p95_ms == pytest.approx(95.5)
    assert row.error_count == 0


def test_aggregate_groups_per_tool_and_counts_errors(abyss_home: Path) -> None:
    tool_metrics.append_event("alpha", "Bash", 10, exit_code=0)
    tool_metrics.append_event("alpha", "Bash", 20, exit_code=1)
    tool_metrics.append_event("alpha", "Read", 5, exit_code=0)

    rows_by_tool = {row.tool: row for row in tool_metrics.aggregate("alpha")}
    assert rows_by_tool["Bash"].count == 2
    assert rows_by_tool["Bash"].error_count == 1
    assert rows_by_tool["Read"].error_count == 0
    # Most-frequent tool comes first.
    rows_in_order = tool_metrics.aggregate("alpha")
    assert rows_in_order[0].tool == "Bash"


def test_aggregate_counts_outcome_failure_without_exit_code(abyss_home: Path) -> None:
    """PostToolUseFailure events have outcome=failure but no exit_code —
    they must still count as errors."""
    tool_metrics.append_event("alpha", "Bash", 10, exit_code=0, extra={"outcome": "success"})
    tool_metrics.append_event("alpha", "Bash", 20, extra={"outcome": "failure"})
    tool_metrics.append_event("alpha", "Bash", 30, extra={"outcome": "failure"})

    rows = tool_metrics.aggregate("alpha")
    assert rows[0].count == 3
    assert rows[0].error_count == 2


def test_aggregate_handles_missing_directory(abyss_home: Path) -> None:
    assert tool_metrics.aggregate("never-existed") == []


def test_aggregate_skips_corrupt_lines(abyss_home: Path) -> None:
    metrics_dir = tool_metrics.metrics_directory("alpha")
    metrics_dir.mkdir(parents=True)
    target = metrics_dir / "20260430.jsonl"
    target.write_text(
        '{"ts": "x", "tool": "Bash", "duration_ms": 10}\n'
        "not-json-at-all\n"
        '{"ts": "x", "tool": "Bash", "duration_ms": "oops"}\n'
        '{"ts": "x", "tool": "Bash", "duration_ms": 20}\n'
    )

    rows = tool_metrics.aggregate("alpha")
    assert rows[0].tool == "Bash"
    assert rows[0].count == 2  # only the two well-formed rows


def test_iter_events_orders_by_filename(abyss_home: Path) -> None:
    """Older days come first when iterating."""
    metrics_dir = tool_metrics.metrics_directory("alpha")
    metrics_dir.mkdir(parents=True)
    (metrics_dir / "20260428.jsonl").write_text(
        '{"tool": "Read", "duration_ms": 1, "ts": "older"}\n'
    )
    (metrics_dir / "20260430.jsonl").write_text(
        '{"tool": "Bash", "duration_ms": 2, "ts": "newer"}\n'
    )

    timestamps = [event["ts"] for event in tool_metrics.iter_events("alpha")]
    assert timestamps == ["older", "newer"]
