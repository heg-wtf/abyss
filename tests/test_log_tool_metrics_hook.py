"""Tests for the PostToolUse hook entry point ``log_tool_metrics``."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from abyss.hooks import log_tool_metrics


@pytest.fixture
def abyss_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("AI_AGENT", "abyss")
    home = tmp_path / ".abyss"
    monkeypatch.setenv("ABYSS_HOME", str(home))
    return home


def _stdin(payload: dict) -> io.StringIO:
    return io.StringIO(json.dumps(payload))


# ─── guard: not invoked by abyss ─────────────────────────────────────────


def test_no_op_when_ai_agent_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_AGENT", raising=False)
    with patch("abyss.tool_metrics.append_event") as append:
        assert log_tool_metrics.main(stdin=_stdin({"cwd": "/tmp"})) == 0
    append.assert_not_called()


def test_no_op_when_ai_agent_other(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_AGENT", "claude-code")
    with patch("abyss.tool_metrics.append_event") as append:
        assert log_tool_metrics.main(stdin=_stdin({"cwd": "/tmp"})) == 0
    append.assert_not_called()


# ─── stdin handling ──────────────────────────────────────────────────────


def test_no_op_on_empty_stdin(abyss_env: Path) -> None:
    with patch("abyss.tool_metrics.append_event") as append:
        assert log_tool_metrics.main(stdin=io.StringIO("")) == 0
    append.assert_not_called()


def test_no_op_on_invalid_json(abyss_env: Path) -> None:
    with patch("abyss.tool_metrics.append_event") as append:
        assert log_tool_metrics.main(stdin=io.StringIO("{bad")) == 0
    append.assert_not_called()


def test_no_op_when_payload_lacks_cwd(abyss_env: Path) -> None:
    with patch("abyss.tool_metrics.append_event") as append:
        assert log_tool_metrics.main(stdin=_stdin({"tool_name": "Bash"})) == 0
    append.assert_not_called()


# ─── happy path ──────────────────────────────────────────────────────────


def test_records_event_for_resolved_bot(abyss_env: Path) -> None:
    session = abyss_env / "bots" / "alpha" / "sessions" / "chat_1"
    session.mkdir(parents=True)
    payload = {
        "cwd": str(session),
        "tool_name": "Bash",
        "duration_ms": 123.0,
        "session_id": "abc-1",
        "tool_response": {"exit_code": 0},
    }

    assert log_tool_metrics.main(stdin=_stdin(payload)) == 0

    # File written by tool_metrics.append_event under the correct bot.
    metrics_files = list((abyss_env / "bots" / "alpha" / "tool_metrics").glob("*.jsonl"))
    assert len(metrics_files) == 1
    rows = [json.loads(line) for line in metrics_files[0].read_text().splitlines() if line.strip()]
    assert rows[0]["tool"] == "Bash"
    assert rows[0]["duration_ms"] == 123.0
    assert rows[0]["exit_code"] == 0
    assert rows[0]["session_id"] == "abc-1"
    # Default outcome is success when ABYSS_HOOK_OUTCOME is unset.
    assert rows[0]["outcome"] == "success"


def test_records_failure_outcome_from_env(abyss_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When CC fires PostToolUseFailure, the wrapper sets
    ABYSS_HOOK_OUTCOME=failure and the event is tagged accordingly."""
    monkeypatch.setenv("ABYSS_HOOK_OUTCOME", "failure")

    session = abyss_env / "bots" / "alpha" / "sessions" / "chat_1"
    session.mkdir(parents=True)
    payload = {
        "cwd": str(session),
        "tool_name": "Bash",
        "duration_ms": 50.0,
        "tool_response": {"error": "boom"},
    }

    assert log_tool_metrics.main(stdin=_stdin(payload)) == 0

    rows_path = next((abyss_env / "bots" / "alpha" / "tool_metrics").glob("*.jsonl"))
    rows = [json.loads(line) for line in rows_path.read_text().splitlines() if line.strip()]
    assert rows[0]["outcome"] == "failure"


def test_invalid_outcome_env_falls_back_to_success(
    abyss_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bogus ABYSS_HOOK_OUTCOME value defaults back to success rather
    than corrupting the metrics with arbitrary strings."""
    monkeypatch.setenv("ABYSS_HOOK_OUTCOME", "explosion")

    session = abyss_env / "bots" / "alpha" / "sessions" / "chat_1"
    session.mkdir(parents=True)
    payload = {"cwd": str(session), "tool_name": "Bash", "duration_ms": 5.0}

    assert log_tool_metrics.main(stdin=_stdin(payload)) == 0

    rows_path = next((abyss_env / "bots" / "alpha" / "tool_metrics").glob("*.jsonl"))
    rows = [json.loads(line) for line in rows_path.read_text().splitlines() if line.strip()]
    assert rows[0]["outcome"] == "success"


def test_reads_duration_from_nested_tool_response(abyss_env: Path) -> None:
    session = abyss_env / "bots" / "alpha" / "sessions" / "chat_1"
    session.mkdir(parents=True)
    payload = {
        "cwd": str(session),
        "tool_name": "Bash",
        "tool_response": {"duration_ms": 77.0},
    }

    assert log_tool_metrics.main(stdin=_stdin(payload)) == 0

    rows_path = next((abyss_env / "bots" / "alpha" / "tool_metrics").glob("*.jsonl"))
    rows = [json.loads(line) for line in rows_path.read_text().splitlines() if line.strip()]
    assert rows[0]["duration_ms"] == 77.0


def test_no_op_when_tool_or_duration_missing(abyss_env: Path) -> None:
    session = abyss_env / "bots" / "alpha" / "sessions" / "chat_1"
    session.mkdir(parents=True)
    with patch("abyss.tool_metrics.append_event") as append:
        # Missing tool_name
        assert log_tool_metrics.main(stdin=_stdin({"cwd": str(session)})) == 0
        # Missing duration
        assert (
            log_tool_metrics.main(
                stdin=_stdin({"cwd": str(session), "tool_name": "Bash"}),
            )
            == 0
        )
    append.assert_not_called()


def test_swallows_append_event_exception(abyss_env: Path) -> None:
    session = abyss_env / "bots" / "alpha" / "sessions" / "chat_1"
    session.mkdir(parents=True)
    payload = {"cwd": str(session), "tool_name": "Bash", "duration_ms": 5.0}

    with patch("abyss.tool_metrics.append_event", side_effect=RuntimeError("disk full")):
        assert log_tool_metrics.main(stdin=_stdin(payload)) == 0
