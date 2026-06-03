"""Unit tests for the ``propose_skill`` MCP server (Phase 5)."""

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
    from abyss.mcp_servers import propose_skill

    response = _rpc(propose_skill.serve, 1, "initialize")
    assert response["result"]["serverInfo"]["name"] == "abyss-propose-skill"


def test_tools_list_exposes_single_tool(abyss_home_with_bot) -> None:
    from abyss.mcp_servers import propose_skill

    response = _rpc(propose_skill.serve, 2, "tools/list")
    names = [t["name"] for t in response["result"]["tools"]]
    assert names == ["propose_skill"]


def test_propose_skill_happy_path_writes_yaml(
    abyss_home_with_bot, monkeypatch: pytest.MonkeyPatch
) -> None:
    from abyss.mcp_servers import propose_skill
    from abyss.skill_proposals import list_proposals

    # Stub web_push to avoid the asyncio.run side effect under pytest.
    monkeypatch.setattr("abyss.mcp_servers.propose_skill._maybe_notify", lambda *_a, **_k: None)

    response = _rpc(
        propose_skill.serve,
        3,
        "tools/call",
        {
            "name": "propose_skill",
            "arguments": {
                "candidate_url": "https://github.com/owner/cool",
                "reason": "needs stripe fetcher",
            },
        },
    )
    body = json.loads(response["result"]["content"][0]["text"])
    assert body["bot"] == "anne"
    assert body["candidate_url"] == "https://github.com/owner/cool"
    rows = list_proposals("anne")
    assert len(rows) == 1
    assert rows[0].reasons == ["needs stripe fetcher"]


def test_propose_skill_rejects_non_github_url(
    abyss_home_with_bot, monkeypatch: pytest.MonkeyPatch
) -> None:
    from abyss.mcp_servers import propose_skill

    monkeypatch.setattr("abyss.mcp_servers.propose_skill._maybe_notify", lambda *_a, **_k: None)

    response = _rpc(
        propose_skill.serve,
        4,
        "tools/call",
        {
            "name": "propose_skill",
            "arguments": {
                "candidate_url": "https://example.com/owner/cool",
                "reason": "x",
            },
        },
    )
    payload = response["result"]
    assert payload.get("isError") is True
    assert "github.com" in payload["content"][0]["text"].lower()


def test_propose_skill_requires_candidate_and_reason(
    abyss_home_with_bot,
) -> None:
    from abyss.mcp_servers import propose_skill

    response = _rpc(
        propose_skill.serve,
        5,
        "tools/call",
        {"name": "propose_skill", "arguments": {"candidate_url": "", "reason": "x"}},
    )
    assert response["result"].get("isError") is True


def test_propose_skill_rejects_bad_alternative_url(
    abyss_home_with_bot, monkeypatch: pytest.MonkeyPatch
) -> None:
    from abyss.mcp_servers import propose_skill

    monkeypatch.setattr("abyss.mcp_servers.propose_skill._maybe_notify", lambda *_a, **_k: None)

    response = _rpc(
        propose_skill.serve,
        6,
        "tools/call",
        {
            "name": "propose_skill",
            "arguments": {
                "candidate_url": "https://github.com/owner/repo",
                "reason": "x",
                "alternative_urls": ["https://bad.example/x"],
            },
        },
    )
    assert response["result"].get("isError") is True


def test_propose_skill_dedups_repeated_call(
    abyss_home_with_bot, monkeypatch: pytest.MonkeyPatch
) -> None:
    from abyss.mcp_servers import propose_skill
    from abyss.skill_proposals import list_proposals

    monkeypatch.setattr("abyss.mcp_servers.propose_skill._maybe_notify", lambda *_a, **_k: None)

    args = {
        "name": "propose_skill",
        "arguments": {
            "candidate_url": "https://github.com/owner/repo",
            "reason": "first call",
        },
    }
    _rpc(propose_skill.serve, 7, "tools/call", args)
    args["arguments"]["reason"] = "second call"
    _rpc(propose_skill.serve, 8, "tools/call", args)
    rows = list_proposals("anne")
    assert len(rows) == 1
    assert rows[0].reasons == ["first call", "second call"]


def test_bot_resolution_failure(tmp_path, monkeypatch) -> None:
    from abyss.mcp_servers import propose_skill

    monkeypatch.chdir(tmp_path)  # outside any bots/ ancestor
    response = _rpc(
        propose_skill.serve,
        9,
        "tools/call",
        {
            "name": "propose_skill",
            "arguments": {
                "candidate_url": "https://github.com/x/y",
                "reason": "anything",
            },
        },
    )
    assert response["result"].get("isError") is True
    assert "resolve bot" in response["result"]["content"][0]["text"]


def test_unknown_tool(abyss_home_with_bot) -> None:
    from abyss.mcp_servers import propose_skill

    response = _rpc(
        propose_skill.serve,
        10,
        "tools/call",
        {"name": "bogus", "arguments": {}},
    )
    assert "error" in response
