"""Unit tests for the ``recall_fact`` MCP server.

The server runs over JSON-RPC stdio. These tests drive it through
``io.StringIO`` pipes instead of spawning a subprocess so they stay
fast and deterministic.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


@pytest.fixture
def abyss_home_with_bot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Set ABYSS_HOME and create one bot directory + chdir into it.

    ``recall_fact`` resolves the bot from cwd, so the tests place us
    under ``bots/anne/sessions/<id>`` (a realistic working dir).
    """
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
    bot_dir = tmp_path / "bots" / "anne"
    session_dir = bot_dir / "sessions" / "chat_test"
    session_dir.mkdir(parents=True)
    monkeypatch.chdir(session_dir)
    return tmp_path, bot_dir


def _rpc(server_call, request_id: int, method: str, params: dict | None = None) -> dict:
    """Drive one JSON-RPC roundtrip through ``serve`` using StringIO."""
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
    from abyss.mcp_servers import recall_fact

    response = _rpc(recall_fact.serve, 1, "initialize")
    assert response["result"]["serverInfo"]["name"] == "abyss-recall-fact"


def test_tools_list_includes_both_tools(abyss_home_with_bot) -> None:
    from abyss.mcp_servers import recall_fact

    response = _rpc(recall_fact.serve, 2, "tools/list")
    names = {t["name"] for t in response["result"]["tools"]}
    assert names == {"recall_fact", "recent_episodes"}


def test_recall_fact_returns_persisted_rows(abyss_home_with_bot) -> None:
    from abyss.episodes import Fact, upsert_fact
    from abyss.mcp_servers import recall_fact

    upsert_fact("anne", Fact(subject="release", claim="v2026.06.02", confidence=0.9))
    response = _rpc(
        recall_fact.serve,
        3,
        "tools/call",
        {"name": "recall_fact", "arguments": {"subject": "release"}},
    )
    text = response["result"]["content"][0]["text"]
    body = json.loads(text)
    assert body["bot"] == "anne"
    assert body["facts"][0]["claim"] == "v2026.06.02"


def test_recall_fact_no_match_returns_friendly_text(abyss_home_with_bot) -> None:
    from abyss.episodes import Fact, upsert_fact
    from abyss.mcp_servers import recall_fact

    upsert_fact("anne", Fact(subject="x", claim="y", confidence=0.4))
    response = _rpc(
        recall_fact.serve,
        4,
        "tools/call",
        {"name": "recall_fact", "arguments": {"subject": "x"}},  # below default min
    )
    assert response["result"]["content"][0]["text"] == "(no matching facts)"


def test_recent_episodes_returns_filtered_rows(
    abyss_home_with_bot, monkeypatch: pytest.MonkeyPatch
) -> None:
    from abyss.episodes import Episode, append_episode
    from abyss.mcp_servers import recall_fact

    today = datetime.now(timezone.utc).date()
    # Recent: included.
    append_episode(
        "anne",
        Episode(
            ts=today.isoformat(),
            date=today.isoformat(),
            kind="decision",
            summary="ship phase 4",
        ),
    )
    # Way back: excluded by ``days=7``.
    append_episode(
        "anne",
        Episode(
            ts="2020-01-01",
            date="2020-01-01",
            kind="decision",
            summary="ancient",
        ),
    )
    response = _rpc(
        recall_fact.serve,
        5,
        "tools/call",
        {"name": "recent_episodes", "arguments": {"days": 7}},
    )
    body = json.loads(response["result"]["content"][0]["text"])
    summaries = [e["summary"] for e in body["episodes"]]
    assert summaries == ["ship phase 4"]


def test_unknown_tool_returns_error(abyss_home_with_bot) -> None:
    from abyss.mcp_servers import recall_fact

    response = _rpc(
        recall_fact.serve,
        6,
        "tools/call",
        {"name": "bogus", "arguments": {}},
    )
    assert "error" in response
    assert response["error"]["code"] == -32601


def test_bot_resolution_fails_outside_bots(tmp_path, monkeypatch) -> None:
    from abyss.mcp_servers import recall_fact

    monkeypatch.chdir(tmp_path)  # not under bots/
    response = _rpc(
        recall_fact.serve,
        7,
        "tools/call",
        {"name": "recall_fact", "arguments": {}},
    )
    payload = response["result"]
    assert payload.get("isError") is True
    assert "resolve bot" in payload["content"][0]["text"]
