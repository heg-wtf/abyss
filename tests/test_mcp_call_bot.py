"""Unit tests for the ``call_bot`` MCP server (Phase 7.0)."""

from __future__ import annotations

import asyncio
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml


@pytest.fixture
def abyss_home_with_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path]:
    """Set ABYSS_HOME with two bots ``anne`` (caller) and ``kim`` (peer).

    chdir into anne's chat session so the caller-resolution heuristic
    fires identically to the production code path.
    """
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
    monkeypatch.delenv("ABYSS_CALL_BOT_DEPTH", raising=False)

    config = {
        "bots": [
            {"name": "anne", "path": str(tmp_path / "bots" / "anne")},
            {"name": "kim", "path": str(tmp_path / "bots" / "kim")},
        ],
        "settings": {"language": "english", "timezone": "UTC"},
    }
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(config))

    for name in ("anne", "kim"):
        bot_dir = tmp_path / "bots" / name
        bot_dir.mkdir(parents=True)
        bot_dir.joinpath("bot.yaml").write_text(
            yaml.safe_dump({"display_name": name, "personality": "x", "role": "y"})
        )
    anne_session = tmp_path / "bots" / "anne" / "sessions" / "chat_test"
    anne_session.mkdir(parents=True)
    monkeypatch.chdir(anne_session)
    return tmp_path, tmp_path / "bots" / "anne", tmp_path / "bots" / "kim"


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


@dataclass
class _Reply:
    text: str
    session_id: str = "s"


class _StubBackend:
    """Records the LLMRequest it received, returns canned reply."""

    def __init__(self, reply: str = "ok") -> None:
        self.reply = reply
        self.received: Any = None

    async def run(self, request: Any) -> _Reply:
        self.received = request
        return _Reply(text=self.reply)


# ─── basic protocol ──────────────────────────────────────────────────────


def test_initialize_returns_server_info(abyss_home_with_pair) -> None:
    from abyss.mcp_servers import call_bot

    resp = _rpc(call_bot.serve, 1, "initialize")
    assert resp["result"]["serverInfo"]["name"] == "abyss-call-bot"


def test_tools_list_exposes_single_tool(abyss_home_with_pair) -> None:
    from abyss.mcp_servers import call_bot

    resp = _rpc(call_bot.serve, 2, "tools/list")
    assert [t["name"] for t in resp["result"]["tools"]] == ["call_bot"]


# ─── happy path ──────────────────────────────────────────────────────────


def test_call_bot_routes_to_peer_and_returns_reply(
    abyss_home_with_pair, monkeypatch: pytest.MonkeyPatch
) -> None:
    from abyss.mcp_servers import call_bot

    stub = _StubBackend(reply="kim says hi")
    monkeypatch.setattr("abyss.llm.registry.get_or_create", lambda *_a, **_k: stub)

    resp = _rpc(
        call_bot.serve,
        3,
        "tools/call",
        {
            "name": "call_bot",
            "arguments": {"bot": "kim", "message": "hi kim"},
        },
    )
    text = resp["result"]["content"][0]["text"]
    assert text == "kim says hi"
    assert stub.received.user_prompt == "hi kim"
    assert stub.received.bot_name == "kim"
    # Session key encodes (caller, peer, depth-after-increment).
    assert "peer_call:anne:kim:1" == stub.received.session_key


# ─── validation ──────────────────────────────────────────────────────────


def test_call_bot_rejects_self_call(abyss_home_with_pair, monkeypatch: pytest.MonkeyPatch) -> None:
    from abyss.mcp_servers import call_bot

    # Backend should not be invoked when caller == peer.
    monkeypatch.setattr(
        "abyss.llm.registry.get_or_create",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not call peer")),
    )
    resp = _rpc(
        call_bot.serve,
        4,
        "tools/call",
        {"name": "call_bot", "arguments": {"bot": "anne", "message": "hi self"}},
    )
    assert resp["result"].get("isError") is True
    assert "self-call" in resp["result"]["content"][0]["text"]


def test_call_bot_unknown_peer(abyss_home_with_pair) -> None:
    from abyss.mcp_servers import call_bot

    resp = _rpc(
        call_bot.serve,
        5,
        "tools/call",
        {"name": "call_bot", "arguments": {"bot": "ghost", "message": "x"}},
    )
    assert resp["result"].get("isError") is True
    assert "not found" in resp["result"]["content"][0]["text"]


def test_call_bot_empty_message_rejected(abyss_home_with_pair) -> None:
    from abyss.mcp_servers import call_bot

    resp = _rpc(
        call_bot.serve,
        6,
        "tools/call",
        {"name": "call_bot", "arguments": {"bot": "kim", "message": "   "}},
    )
    assert resp["result"].get("isError") is True
    assert "message is required" in resp["result"]["content"][0]["text"]


def test_call_bot_message_too_large(abyss_home_with_pair) -> None:
    from abyss.mcp_servers import call_bot

    payload = "a" * 5000
    resp = _rpc(
        call_bot.serve,
        7,
        "tools/call",
        {"name": "call_bot", "arguments": {"bot": "kim", "message": payload}},
    )
    assert resp["result"].get("isError") is True
    assert "too long" in resp["result"]["content"][0]["text"]


# ─── depth guard ─────────────────────────────────────────────────────────


def test_call_bot_depth_cap(abyss_home_with_pair, monkeypatch: pytest.MonkeyPatch) -> None:
    from abyss.mcp_servers import call_bot

    monkeypatch.setenv(call_bot.DEPTH_ENV, str(call_bot.MAX_DEPTH))
    monkeypatch.setattr(
        "abyss.llm.registry.get_or_create",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not recurse")),
    )
    resp = _rpc(
        call_bot.serve,
        8,
        "tools/call",
        {"name": "call_bot", "arguments": {"bot": "kim", "message": "x"}},
    )
    assert resp["result"].get("isError") is True
    assert "depth cap" in resp["result"]["content"][0]["text"]


def test_call_bot_increments_depth_during_call(
    abyss_home_with_pair, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Inside the backend.run() coroutine the depth env should be N+1."""
    from abyss.mcp_servers import call_bot

    observed: dict[str, str] = {}

    class _PeekBackend:
        async def run(self, request: Any) -> _Reply:
            import os

            observed["env"] = os.environ.get(call_bot.DEPTH_ENV, "")
            return _Reply(text="ok")

    monkeypatch.setattr("abyss.llm.registry.get_or_create", lambda *_a, **_k: _PeekBackend())
    _rpc(
        call_bot.serve,
        9,
        "tools/call",
        {"name": "call_bot", "arguments": {"bot": "kim", "message": "x"}},
    )
    assert observed["env"] == "1"


def test_call_bot_restores_depth_env_after_call(
    abyss_home_with_pair, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After the call returns, the env counter must roll back to the caller value."""
    import os

    from abyss.mcp_servers import call_bot

    monkeypatch.setenv(call_bot.DEPTH_ENV, "1")  # caller is at depth 1
    monkeypatch.setattr("abyss.llm.registry.get_or_create", lambda *_a, **_k: _StubBackend())
    _rpc(
        call_bot.serve,
        10,
        "tools/call",
        {"name": "call_bot", "arguments": {"bot": "kim", "message": "x"}},
    )
    assert os.environ.get(call_bot.DEPTH_ENV) == "1"


# ─── timeout + caller resolution failures ────────────────────────────────


def test_call_bot_timeout_propagates(abyss_home_with_pair, monkeypatch: pytest.MonkeyPatch) -> None:
    from abyss.mcp_servers import call_bot

    class _SlowBackend:
        async def run(self, request: Any) -> _Reply:
            await asyncio.sleep(5)
            return _Reply(text="too late")

    monkeypatch.setattr("abyss.llm.registry.get_or_create", lambda *_a, **_k: _SlowBackend())
    resp = _rpc(
        call_bot.serve,
        11,
        "tools/call",
        {
            "name": "call_bot",
            "arguments": {"bot": "kim", "message": "x", "timeout": 1},
        },
    )
    assert resp["result"].get("isError") is True
    assert "timed out" in resp["result"]["content"][0]["text"]


def test_call_bot_caller_resolution_failure(tmp_path, monkeypatch) -> None:
    from abyss.mcp_servers import call_bot

    monkeypatch.chdir(tmp_path)  # not under bots/
    resp = _rpc(
        call_bot.serve,
        12,
        "tools/call",
        {"name": "call_bot", "arguments": {"bot": "kim", "message": "x"}},
    )
    assert resp["result"].get("isError") is True
    assert "resolve caller" in resp["result"]["content"][0]["text"]


def test_unknown_tool_returns_error(abyss_home_with_pair) -> None:
    from abyss.mcp_servers import call_bot

    resp = _rpc(
        call_bot.serve,
        13,
        "tools/call",
        {"name": "bogus", "arguments": {}},
    )
    assert "error" in resp
