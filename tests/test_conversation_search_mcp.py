"""Tests for the conversation_search MCP stdio server."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from abyss import conversation_index
from abyss.mcp_servers import conversation_search as srv


def _serve_lines(
    db_path: Path | None, requests: list[dict], monkeypatch: pytest.MonkeyPatch
) -> list[dict]:
    if db_path is not None:
        monkeypatch.setenv("ABYSS_CONVERSATION_DB", str(db_path))
    else:
        monkeypatch.delenv("ABYSS_CONVERSATION_DB", raising=False)

    stdin = io.StringIO("".join(json.dumps(r) + "\n" for r in requests))
    stdout = io.StringIO()
    srv.serve(stdin=stdin, stdout=stdout)
    out_lines = stdout.getvalue().splitlines()
    return [json.loads(line) for line in out_lines if line.strip()]


# ─── case 1: tools/list exposes search_conversations ─────────────────────


def test_tools_list_exposes_search_conversations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    responses = _serve_lines(
        tmp_path / "convo.db",
        [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}],
        monkeypatch,
    )
    assert len(responses) == 1
    tools = responses[0]["result"]["tools"]
    assert len(tools) == 1
    assert tools[0]["name"] == "search_conversations"
    assert "query" in tools[0]["inputSchema"]["required"]


# ─── case 2: tools/call returns hits ─────────────────────────────────────


def test_tools_call_returns_hits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "convo.db"
    conversation_index.append(db, chat_id="chat_42", role="user", content="강남 카페 미팅 좋았어")

    responses = _serve_lines(
        db,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "search_conversations", "arguments": {"query": "강남"}},
            }
        ],
        monkeypatch,
    )
    assert len(responses) == 1
    content = responses[0]["result"]["content"]
    assert len(content) == 1
    assert content[0]["type"] == "text"
    assert "강남" in content[0]["text"]
    assert "chat_42" in content[0]["text"]


# ─── case 3: missing env var → error result ──────────────────────────────


def test_tools_call_without_db_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    responses = _serve_lines(
        None,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "search_conversations", "arguments": {"query": "x"}},
            }
        ],
        monkeypatch,
    )
    assert responses[0]["result"]["isError"] is True
    assert "ABYSS_CONVERSATION_DB" in responses[0]["result"]["content"][0]["text"]


# ─── case 4: missing DB file → empty result ──────────────────────────────


def test_tools_call_with_missing_db_returns_no_hits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "missing.db"
    responses = _serve_lines(
        db,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "search_conversations",
                    "arguments": {"query": "anything"},
                },
            }
        ],
        monkeypatch,
    )
    assert (
        "no conversation messages matched" in responses[0]["result"]["content"][0]["text"].lower()
    )


# ─── case 5: invalid limit clamps to default ──────────────────────────────


def test_tools_call_invalid_limit_clamps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "convo.db"
    conversation_index.append(db, chat_id="chat_1", role="user", content="apple")

    responses = _serve_lines(
        db,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "search_conversations",
                    "arguments": {"query": "apple", "limit": -50},
                },
            }
        ],
        monkeypatch,
    )
    # negative clamps up to 1 — still finds the apple message
    assert "apple" in responses[0]["result"]["content"][0]["text"]


# ─── case 6: unicode + emoji round-trip ──────────────────────────────────


def test_unicode_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "convo.db"
    conversation_index.append(db, chat_id="chat_1", role="user", content="🦞 abyss 야간 미션 시작")

    responses = _serve_lines(
        db,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "search_conversations",
                    "arguments": {"query": "abyss"},
                },
            }
        ],
        monkeypatch,
    )
    text = responses[0]["result"]["content"][0]["text"]
    assert "🦞" in text or "abyss" in text


# ─── initialize handshake ─────────────────────────────────────────────────


def test_initialize_returns_capabilities(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    responses = _serve_lines(
        tmp_path / "convo.db",
        [{"jsonrpc": "2.0", "id": 1, "method": "initialize"}],
        monkeypatch,
    )
    result = responses[0]["result"]
    assert result["protocolVersion"]
    assert result["capabilities"]["tools"]["listChanged"] is False
    assert result["serverInfo"]["name"] == srv.SERVER_NAME


def test_unknown_method_returns_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    responses = _serve_lines(
        tmp_path / "convo.db",
        [{"jsonrpc": "2.0", "id": 1, "method": "tools/who_knows"}],
        monkeypatch,
    )
    assert responses[0]["error"]["code"] == -32601


def test_notification_yields_no_response(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    responses = _serve_lines(
        tmp_path / "convo.db",
        [{"jsonrpc": "2.0", "method": "notifications/initialized"}],
        monkeypatch,
    )
    assert responses == []


def test_unknown_tool_name_returns_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    responses = _serve_lines(
        tmp_path / "convo.db",
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "wat", "arguments": {}},
            }
        ],
        monkeypatch,
    )
    assert responses[0]["error"]["code"] == -32601


def test_blank_query_reports_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "convo.db"
    conversation_index.append(db, chat_id="chat_1", role="user", content="apple")
    responses = _serve_lines(
        db,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "search_conversations",
                    "arguments": {"query": "   "},
                },
            }
        ],
        monkeypatch,
    )
    assert responses[0]["result"]["isError"] is True
