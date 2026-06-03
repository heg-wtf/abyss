"""Unit tests for ``record_progress`` MCP server (Phase 6)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest


@pytest.fixture
def abyss_home_with_bot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
    bot_dir = tmp_path / "bots" / "anne"
    session_dir = bot_dir / "sessions" / "chat_test"
    session_dir.mkdir(parents=True)
    monkeypatch.chdir(session_dir)
    return tmp_path, bot_dir


def _rpc(server_call, request_id: int, method: str, params: dict | None = None) -> dict:
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        payload["params"] = params
    stdin = io.StringIO(json.dumps(payload) + "\n")
    stdout = io.StringIO()
    server_call(stdin=stdin, stdout=stdout)
    raw = stdout.getvalue().strip().splitlines()
    assert raw, "server produced no output"
    return json.loads(raw[0])


def test_initialize_returns_server_info(abyss_home_with_bot) -> None:
    from abyss.mcp_servers import record_progress

    resp = _rpc(record_progress.serve, 1, "initialize")
    assert resp["result"]["serverInfo"]["name"] == "abyss-record-progress"


def test_tools_list_exposes_single_tool(abyss_home_with_bot) -> None:
    from abyss.mcp_servers import record_progress

    resp = _rpc(record_progress.serve, 2, "tools/list")
    assert [t["name"] for t in resp["result"]["tools"]] == ["record_progress"]


def test_record_progress_appends_to_existing_goal(abyss_home_with_bot) -> None:
    from abyss.goals import add_goal, get_goal
    from abyss.mcp_servers import record_progress

    goal = add_goal("anne", "Ship blog")
    resp = _rpc(
        record_progress.serve,
        3,
        "tools/call",
        {
            "name": "record_progress",
            "arguments": {"goal_id": goal.id, "note": "addressed review"},
        },
    )
    body = json.loads(resp["result"]["content"][0]["text"])
    assert body["bot"] == "anne"
    assert body["goal_id"] == goal.id
    assert get_goal("anne", goal.id).progress[-1].note == "addressed review"


def test_record_progress_unknown_goal(abyss_home_with_bot) -> None:
    from abyss.mcp_servers import record_progress

    resp = _rpc(
        record_progress.serve,
        4,
        "tools/call",
        {
            "name": "record_progress",
            "arguments": {"goal_id": "ghost", "note": "x"},
        },
    )
    assert resp["result"].get("isError") is True
    assert "goal not found" in resp["result"]["content"][0]["text"]


def test_record_progress_empty_note(abyss_home_with_bot) -> None:
    from abyss.goals import add_goal
    from abyss.mcp_servers import record_progress

    goal = add_goal("anne", "Ship blog")
    resp = _rpc(
        record_progress.serve,
        5,
        "tools/call",
        {
            "name": "record_progress",
            "arguments": {"goal_id": goal.id, "note": "  "},
        },
    )
    assert resp["result"].get("isError") is True
    assert "note is required" in resp["result"]["content"][0]["text"]


def test_record_progress_message_too_long(abyss_home_with_bot) -> None:
    from abyss.goals import add_goal
    from abyss.mcp_servers import record_progress

    goal = add_goal("anne", "Ship blog")
    resp = _rpc(
        record_progress.serve,
        6,
        "tools/call",
        {
            "name": "record_progress",
            "arguments": {"goal_id": goal.id, "note": "x" * 3000},
        },
    )
    assert resp["result"].get("isError") is True
    assert "too long" in resp["result"]["content"][0]["text"]


def test_record_progress_value_must_be_number(abyss_home_with_bot) -> None:
    from abyss.goals import add_goal
    from abyss.mcp_servers import record_progress

    goal = add_goal("anne", "Ship blog")
    resp = _rpc(
        record_progress.serve,
        7,
        "tools/call",
        {
            "name": "record_progress",
            "arguments": {"goal_id": goal.id, "note": "ok", "value": "not a num"},
        },
    )
    assert resp["result"].get("isError") is True
    assert "value must be a number" in resp["result"]["content"][0]["text"]


def test_record_progress_bot_resolution_failure(tmp_path, monkeypatch) -> None:
    from abyss.mcp_servers import record_progress

    monkeypatch.chdir(tmp_path)
    resp = _rpc(
        record_progress.serve,
        8,
        "tools/call",
        {
            "name": "record_progress",
            "arguments": {"goal_id": "anything", "note": "x"},
        },
    )
    assert resp["result"].get("isError") is True
    assert "resolve bot" in resp["result"]["content"][0]["text"]


def test_unknown_tool(abyss_home_with_bot) -> None:
    from abyss.mcp_servers import record_progress

    resp = _rpc(
        record_progress.serve,
        9,
        "tools/call",
        {"name": "bogus", "arguments": {}},
    )
    assert "error" in resp
