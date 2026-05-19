"""Smoke tests for the about_me MCP stdio server."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest


@pytest.fixture
def abyss_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
    return tmp_path


def _send(server_module, messages: list[dict]) -> list[dict]:
    """Run ``serve`` against an in-memory message script and return replies."""
    payload = "\n".join(json.dumps(message) for message in messages) + "\n"
    stdin = io.StringIO(payload)
    stdout = io.StringIO()
    server_module.serve(stdin=stdin, stdout=stdout)
    stdout.seek(0)
    return [json.loads(line) for line in stdout.read().splitlines() if line.strip()]


def test_initialize_advertises_server(abyss_home: Path) -> None:
    from abyss.mcp_servers import about_me as server

    replies = _send(server, [{"jsonrpc": "2.0", "id": 1, "method": "initialize"}])
    assert replies[0]["result"]["serverInfo"]["name"] == "abyss-about-me"


def test_tools_list_exposes_four_tools(abyss_home: Path) -> None:
    from abyss.mcp_servers import about_me as server

    replies = _send(server, [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
    names = {tool["name"] for tool in replies[0]["result"]["tools"]}
    assert names == {
        "about_me_propose",
        "about_me_get",
        "about_me_list_categories",
        "about_me_search",
    }


def test_propose_tool_writes_entry(abyss_home: Path) -> None:
    from abyss.about_me import load_category
    from abyss.mcp_servers import about_me as server

    replies = _send(
        server,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "about_me_propose",
                    "arguments": {
                        "category": "identity",
                        "key": "name",
                        "value": "ash84",
                    },
                },
            }
        ],
    )

    payload = json.loads(replies[0]["result"]["content"][0]["text"])
    assert payload["action"] == "created"
    assert payload["category"] == "identity"
    assert payload["key"] == "name"

    entries = load_category("identity")
    assert len(entries) == 1
    assert entries[0].status == "propose"


def test_propose_tool_missing_required_fields_returns_error(abyss_home: Path) -> None:
    from abyss.mcp_servers import about_me as server

    replies = _send(
        server,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "about_me_propose",
                    "arguments": {"category": "identity"},
                },
            }
        ],
    )
    assert replies[0]["result"]["isError"] is True


def test_get_tool_returns_entries(abyss_home: Path) -> None:
    from abyss.about_me import AboutEntry, upsert_entry
    from abyss.mcp_servers import about_me as server

    upsert_entry("identity", AboutEntry(key="name", value="ash84"))

    replies = _send(
        server,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "about_me_get",
                    "arguments": {"category": "identity"},
                },
            }
        ],
    )

    payload = json.loads(replies[0]["result"]["content"][0]["text"])
    assert payload["category"] == "identity"
    assert payload["entries"][0]["key"] == "name"


def test_list_categories_tool_returns_counts(abyss_home: Path) -> None:
    from abyss.about_me import AboutEntry, propose_entry, upsert_entry
    from abyss.mcp_servers import about_me as server

    upsert_entry("identity", AboutEntry(key="name", value="ash84"))
    propose_entry("preferences", "lang", "ko")

    replies = _send(
        server,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "about_me_list_categories", "arguments": {}},
            }
        ],
    )
    payload = json.loads(replies[0]["result"]["content"][0]["text"])
    assert payload["identity"]["confirmed"] == 1
    assert payload["preferences"]["propose"] == 1


def test_search_tool_finds_substring(abyss_home: Path) -> None:
    from abyss.about_me import AboutEntry, upsert_entry
    from abyss.mcp_servers import about_me as server

    upsert_entry("relationships", AboutEntry(key="wife-name", value="지혜"))

    replies = _send(
        server,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "about_me_search",
                    "arguments": {"query": "지혜"},
                },
            }
        ],
    )

    payload = json.loads(replies[0]["result"]["content"][0]["text"])
    assert payload["count"] == 1
    assert payload["hits"][0]["category"] == "relationships"


def test_unknown_tool_returns_jsonrpc_error(abyss_home: Path) -> None:
    from abyss.mcp_servers import about_me as server

    replies = _send(
        server,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "about_me_nope", "arguments": {}},
            }
        ],
    )
    assert "error" in replies[0]
    assert replies[0]["error"]["code"] == -32601


def test_unknown_method_returns_jsonrpc_error(abyss_home: Path) -> None:
    from abyss.mcp_servers import about_me as server

    replies = _send(
        server,
        [{"jsonrpc": "2.0", "id": 1, "method": "nonexistent/method"}],
    )
    assert replies[0]["error"]["code"] == -32601
