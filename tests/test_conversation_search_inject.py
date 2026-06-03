"""Tests for conversation_search auto-injection into Claude Code config."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def session_dir(tmp_path: Path) -> Path:
    """Create ``bots/<bot>/sessions/chat_42/`` and return that path."""
    bot_dir = tmp_path / "bots" / "test_bot"
    session = bot_dir / "sessions" / "chat_42"
    session.mkdir(parents=True)
    return session


@pytest.mark.enable_conversation_search
def test_prepare_skill_config_injects_conversation_search(
    session_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When FTS5 is available, _prepare_skill_config writes the MCP entry."""
    from abyss.claude_runner import _prepare_skill_config

    allowed_tools, _ = _prepare_skill_config(str(session_dir), None)

    assert allowed_tools is not None
    assert "mcp__conversation_search__search_conversations" in allowed_tools

    mcp_json = session_dir / ".mcp.json"
    assert mcp_json.exists()
    config = json.loads(mcp_json.read_text())

    server = config["mcpServers"]["conversation_search"]
    assert server["args"] == ["-m", "abyss.mcp_servers.conversation_search"]
    db_env = server["env"]["ABYSS_CONVERSATION_DB"]
    expected = session_dir.parent.parent / "conversation.db"
    assert Path(db_env) == expected.resolve()


def test_prepare_skill_config_skips_when_fts5_unavailable(
    session_dir: Path,
) -> None:
    """Without the ``enable_conversation_search`` marker the auto-inject is off."""
    from abyss.claude_runner import (
        PROPOSE_SKILL_ALLOWED_TOOLS,
        _prepare_skill_config,
    )

    allowed_tools, _ = _prepare_skill_config(str(session_dir), None)
    # FTS5 stubbed False, QMD off, no user skills — only the always-on
    # ``propose_skill`` MCP gets injected (no conversation_search).
    assert allowed_tools is not None
    for tool in PROPOSE_SKILL_ALLOWED_TOOLS:
        assert tool in allowed_tools
    assert not any(
        tool.startswith("mcp__conversation_search__") for tool in allowed_tools
    )
    assert (session_dir / ".mcp.json").exists()


@pytest.mark.enable_conversation_search
def test_prepare_skill_config_skips_for_invalid_session_path(
    tmp_path: Path,
) -> None:
    """Working directories with no ``bots/<name>/`` ancestor are silently skipped."""
    from abyss.claude_runner import _prepare_skill_config

    from abyss.claude_runner import PROPOSE_SKILL_ALLOWED_TOOLS

    shallow = tmp_path / "shallow"
    shallow.mkdir()
    allowed_tools, _ = _prepare_skill_config(str(shallow), None)
    # No ``bots/`` ancestor → bot-scoped MCPs skipped, but the
    # always-on ``propose_skill`` MCP still attaches.
    assert allowed_tools is not None
    for tool in PROPOSE_SKILL_ALLOWED_TOOLS:
        assert tool in allowed_tools
    assert not any(
        tool.startswith("mcp__conversation_search__") for tool in allowed_tools
    )
    assert (shallow / ".mcp.json").exists()


# ─── regression: Codex P2 — bot dir resolution across context types ─────


@pytest.mark.enable_conversation_search
def test_prepare_skill_config_resolves_bot_dir_for_heartbeat(
    tmp_path: Path,
) -> None:
    """Heartbeat working dir is shallower than DM sessions — bot dir
    must still resolve to ``bots/<name>/conversation.db``, not
    ``bots/conversation.db``. Regression for PR #7 review.
    """
    import sys

    from abyss.claude_runner import _prepare_skill_config

    bot_path = tmp_path / "bots" / "alpha"
    heartbeat_dir = bot_path / "heartbeat_sessions"
    heartbeat_dir.mkdir(parents=True)

    allowed_tools, _ = _prepare_skill_config(str(heartbeat_dir), None)

    assert allowed_tools is not None
    config = json.loads((heartbeat_dir / ".mcp.json").read_text())
    server = config["mcpServers"]["conversation_search"]
    assert server["command"] == sys.executable
    db_env = Path(server["env"]["ABYSS_CONVERSATION_DB"]).resolve()
    expected_db = (bot_path / "conversation.db").resolve()
    assert db_env == expected_db


@pytest.mark.enable_conversation_search
def test_prepare_skill_config_resolves_bot_dir_for_cron(
    tmp_path: Path,
) -> None:
    """Cron sessions sit at ``bots/<name>/cron_sessions/<job>/`` —
    DB path must still target the bot's own directory."""
    from abyss.claude_runner import _prepare_skill_config

    bot_path = tmp_path / "bots" / "alpha"
    cron_dir = bot_path / "cron_sessions" / "morning_report"
    cron_dir.mkdir(parents=True)

    allowed_tools, _ = _prepare_skill_config(str(cron_dir), None)

    assert allowed_tools is not None
    config = json.loads((cron_dir / ".mcp.json").read_text())
    server = config["mcpServers"]["conversation_search"]
    db_env = Path(server["env"]["ABYSS_CONVERSATION_DB"]).resolve()
    expected_db = (bot_path / "conversation.db").resolve()
    assert db_env == expected_db


# ─── alwaysLoad: claude code 2.1.121 (Phase 2) ────────────────────────────


@pytest.mark.enable_conversation_search
def test_conversation_search_marked_always_load_by_default(
    session_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default config injects ``alwaysLoad: true`` for conversation_search."""
    monkeypatch.setenv("ABYSS_HOME", str(session_dir.parent.parent.parent / ".abyss"))

    from abyss.claude_runner import _prepare_skill_config

    _prepare_skill_config(str(session_dir), None)

    config = json.loads((session_dir / ".mcp.json").read_text())
    assert config["mcpServers"]["conversation_search"]["alwaysLoad"] is True


@pytest.mark.enable_conversation_search
def test_conversation_search_omits_always_load_when_disabled(
    session_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When mcp_always_load=false, the alwaysLoad key is not emitted."""
    abyss_home = session_dir.parent.parent.parent / ".abyss"
    monkeypatch.setenv("ABYSS_HOME", str(abyss_home))

    from abyss.config import default_config, save_config

    config = default_config()
    config["claude_code"]["mcp_always_load"] = False
    save_config(config)

    from abyss.claude_runner import _prepare_skill_config

    _prepare_skill_config(str(session_dir), None)

    written = json.loads((session_dir / ".mcp.json").read_text())
    assert "alwaysLoad" not in written["mcpServers"]["conversation_search"]


def test_qmd_mcp_server_helper_marks_always_load() -> None:
    """``_qmd_mcp_server(True)`` adds the alwaysLoad flag, ``False`` omits it."""
    from abyss.claude_runner import _qmd_mcp_server

    on = _qmd_mcp_server(True)
    assert on["qmd"]["alwaysLoad"] is True
    assert on["qmd"]["url"] == "http://localhost:8181/mcp"

    off = _qmd_mcp_server(False)
    assert "alwaysLoad" not in off["qmd"]
