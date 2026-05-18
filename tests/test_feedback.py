"""Unit tests for ``abyss.feedback``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def abyss_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
    bot_dir = tmp_path / "bots" / "anne"
    bot_dir.mkdir(parents=True)
    return tmp_path


def test_append_feedback_writes_one_line(abyss_home: Path) -> None:
    from abyss.feedback import append_feedback, feedback_file

    record = append_feedback(
        bot="anne",
        session_id="chat_web_abc",
        turn_id="2026-05-19 08:00:00 UTC",
        signal=1,
    )

    assert record["signal"] == 1
    assert record["bot"] == "anne"
    assert record["session_id"] == "chat_web_abc"

    path = feedback_file("anne")
    assert path.exists()
    lines = path.read_text().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["signal"] == 1
    assert parsed["turn_id"] == "2026-05-19 08:00:00 UTC"
    assert parsed["ts"]


def test_append_feedback_appends_multiple(abyss_home: Path) -> None:
    from abyss.feedback import append_feedback, feedback_file

    append_feedback("anne", "s1", "t1", 1)
    append_feedback("anne", "s1", "t2", 3, note="틀림 — X is not Y")
    append_feedback("anne", "s2", "t3", 2)

    lines = feedback_file("anne").read_text().splitlines()
    assert len(lines) == 3
    signals = [json.loads(line)["signal"] for line in lines]
    assert signals == [1, 3, 2]
    assert json.loads(lines[1])["note"] == "틀림 — X is not Y"


def test_load_feedback_skips_malformed(abyss_home: Path) -> None:
    from abyss.feedback import append_feedback, feedback_file, load_feedback

    append_feedback("anne", "s1", "t1", 1)
    # Inject a malformed line and a blank line.
    with open(feedback_file("anne"), "a", encoding="utf-8") as file:
        file.write("not json\n")
        file.write("\n")
        file.write('{"truncated": "\n')
    append_feedback("anne", "s1", "t2", 2)

    records = load_feedback("anne")
    assert len(records) == 2
    assert [record["signal"] for record in records] == [1, 2]


def test_load_feedback_missing_file_returns_empty(abyss_home: Path) -> None:
    from abyss.feedback import load_feedback

    assert load_feedback("anne") == []


def test_aggregate_counts_signals(abyss_home: Path) -> None:
    from abyss.feedback import aggregate, append_feedback

    for _ in range(3):
        append_feedback("anne", "s1", f"t{_}", 1)
    append_feedback("anne", "s1", "t-meh", 2)
    append_feedback("anne", "s1", "t-wrong", 3)

    summary = aggregate("anne")
    assert summary["total"] == 5
    assert summary["count_by_signal"] == {1: 3, 2: 1, 3: 1}
    assert len(summary["latest_per_turn"]) == 5


def test_aggregate_latest_wins_for_same_turn(abyss_home: Path) -> None:
    from abyss.feedback import aggregate, append_feedback

    append_feedback("anne", "s1", "shared-turn", 3)
    append_feedback("anne", "s1", "shared-turn", 1)
    append_feedback("anne", "s1", "shared-turn", 2)

    summary = aggregate("anne")
    latest = summary["latest_per_turn"]["shared-turn"]
    assert latest["signal"] == 2
    # All three were appended, so total still counts them.
    assert summary["total"] == 3


def test_aggregate_last_entries_limit(abyss_home: Path) -> None:
    from abyss.feedback import aggregate, append_feedback

    for index in range(15):
        append_feedback("anne", "s1", f"t{index}", 1)

    summary = aggregate("anne", last_n=5)
    assert len(summary["last_entries"]) == 5
    # last entries are chronological tail
    assert summary["last_entries"][-1]["turn_id"] == "t14"


def test_aggregate_empty_when_no_records(abyss_home: Path) -> None:
    from abyss.feedback import aggregate

    summary = aggregate("anne")
    assert summary["total"] == 0
    assert summary["count_by_signal"] == {1: 0, 2: 0, 3: 0}
    assert summary["latest_per_turn"] == {}
    assert summary["last_entries"] == []
