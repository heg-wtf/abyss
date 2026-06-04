"""Usage-signal gates for Phase 6 / 7 MCP servers.

``record_progress`` and ``call_bot`` were previously always-on per bot.
Both have free-cost gates that hide the spawn from sessions that can't
legally use the tool — ``record_progress`` needs at least one goal,
``call_bot`` needs at least one peer bot.

These tests pin the gate behavior so that:
1. A fresh bot with no goals does NOT spawn ``record_progress``.
2. A single-bot install does NOT spawn ``call_bot``.
3. ``propose_skill`` stays always-on regardless of state (regression).
4. Once the gates open (goals.yaml has a goal, config has > 1 bot)
   the MCPs do attach.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


def _write_goals(bot_dir: Path, goals: list[dict] | None) -> None:
    """Write ``goals.yaml`` with the given list. None → omit the file."""
    if goals is None:
        return
    bot_dir.mkdir(parents=True, exist_ok=True)
    (bot_dir / "goals.yaml").write_text(yaml.safe_dump(goals, allow_unicode=True), encoding="utf-8")


def _write_config(abyss_home: Path, bot_names: list[str]) -> None:
    """Write ``config.yaml`` with the given bot list."""
    abyss_home.mkdir(parents=True, exist_ok=True)
    (abyss_home / "config.yaml").write_text(
        yaml.safe_dump(
            {"bots": [{"name": n, "path": str(abyss_home / "bots" / n)} for n in bot_names]},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


def _session_dir_for(tmp_path: Path, bot_name: str = "alpha") -> tuple[Path, Path]:
    """Return ``(abyss_home, session_dir)`` rooted at ``tmp_path``.

    Layout: ``tmp_path/.abyss/bots/<bot>/sessions/chat_42/`` — matches
    what production callers pass to ``_prepare_skill_config``.
    """
    abyss_home = tmp_path / ".abyss"
    session_dir = abyss_home / "bots" / bot_name / "sessions" / "chat_42"
    session_dir.mkdir(parents=True)
    return abyss_home, session_dir


def _prep(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    goals: list[dict] | None = None,
    bots: list[str] | None = None,
    bot_name: str = "alpha",
) -> tuple[Path, Path]:
    """Build a temp ABYSS_HOME, write fixtures, return (home, session_dir)."""
    abyss_home, session_dir = _session_dir_for(tmp_path, bot_name)
    monkeypatch.setenv("ABYSS_HOME", str(abyss_home))
    _write_goals(session_dir.parent.parent, goals)
    if bots is not None:
        _write_config(abyss_home, bots)
    return abyss_home, session_dir


# ─── _has_active_goals (unit) ─────────────────────────────────────────────


def test_has_active_goals_returns_false_when_file_missing(tmp_path: Path) -> None:
    from abyss.claude_runner import _has_active_goals

    assert _has_active_goals(tmp_path) is False


def test_has_active_goals_returns_false_when_empty_list(tmp_path: Path) -> None:
    from abyss.claude_runner import _has_active_goals

    (tmp_path / "goals.yaml").write_text("[]", encoding="utf-8")
    assert _has_active_goals(tmp_path) is False


def test_has_active_goals_returns_false_when_yaml_null(tmp_path: Path) -> None:
    from abyss.claude_runner import _has_active_goals

    (tmp_path / "goals.yaml").write_text("", encoding="utf-8")
    assert _has_active_goals(tmp_path) is False


def test_has_active_goals_returns_false_when_yaml_malformed(tmp_path: Path) -> None:
    from abyss.claude_runner import _has_active_goals

    (tmp_path / "goals.yaml").write_text("not: : valid: yaml: [", encoding="utf-8")
    assert _has_active_goals(tmp_path) is False


def test_has_active_goals_returns_true_when_goal_present(tmp_path: Path) -> None:
    from abyss.claude_runner import _has_active_goals

    (tmp_path / "goals.yaml").write_text(
        yaml.safe_dump([{"id": "x", "title": "Smoke"}]), encoding="utf-8"
    )
    assert _has_active_goals(tmp_path) is True


# ─── _record_progress_mcp_server gate ─────────────────────────────────────


def test_record_progress_skipped_without_goals(tmp_path: Path) -> None:
    from abyss.claude_runner import _record_progress_mcp_server

    assert _record_progress_mcp_server(tmp_path) is None


def test_record_progress_attaches_when_goal_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from abyss.claude_runner import _record_progress_mcp_server

    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
    (tmp_path / "goals.yaml").write_text(
        yaml.safe_dump([{"id": "x", "title": "Smoke"}]), encoding="utf-8"
    )
    entry = _record_progress_mcp_server(tmp_path)
    assert entry is not None
    assert "record_progress" in entry
    assert entry["record_progress"]["args"] == ["-m", "abyss.mcp_servers.record_progress"]


# ─── _call_bot_mcp_server gate ────────────────────────────────────────────


def test_call_bot_skipped_with_single_bot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from abyss.claude_runner import _call_bot_mcp_server

    abyss_home = tmp_path / ".abyss"
    monkeypatch.setenv("ABYSS_HOME", str(abyss_home))
    _write_config(abyss_home, ["alpha"])
    assert _call_bot_mcp_server() is None


def test_call_bot_skipped_with_zero_bots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from abyss.claude_runner import _call_bot_mcp_server

    abyss_home = tmp_path / ".abyss"
    monkeypatch.setenv("ABYSS_HOME", str(abyss_home))
    _write_config(abyss_home, [])
    assert _call_bot_mcp_server() is None


def test_call_bot_attaches_with_multiple_bots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from abyss.claude_runner import _call_bot_mcp_server

    abyss_home = tmp_path / ".abyss"
    monkeypatch.setenv("ABYSS_HOME", str(abyss_home))
    _write_config(abyss_home, ["alpha", "beta"])
    entry = _call_bot_mcp_server()
    assert entry is not None
    assert "call_bot" in entry
    assert entry["call_bot"]["env"]["ABYSS_CALL_BOT_DEPTH"] == "0"


def test_call_bot_conservatively_attaches_when_config_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No config.yaml at all → attach (conservative default).

    Test isolation can leave config.yaml absent; the production
    behavior in that branch is to keep the MCP on so we don't silently
    break a feature when the env is incomplete.
    """
    from abyss.claude_runner import _call_bot_mcp_server

    abyss_home = tmp_path / ".abyss"
    abyss_home.mkdir()
    monkeypatch.setenv("ABYSS_HOME", str(abyss_home))
    entry = _call_bot_mcp_server()
    assert entry is not None
    assert "call_bot" in entry


# ─── _prepare_skill_config integration ────────────────────────────────────


def test_prepare_skill_config_skips_both_gates_on_fresh_bot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fresh bot, no goals, single-bot install → neither MCP attaches."""
    from abyss.claude_runner import _prepare_skill_config

    _, session_dir = _prep(tmp_path, monkeypatch, goals=None, bots=["alpha"])

    allowed_tools, _env = _prepare_skill_config(str(session_dir), None)

    assert allowed_tools is not None
    config = json.loads((session_dir / ".mcp.json").read_text())
    servers = config["mcpServers"]
    assert "record_progress" not in servers
    assert "call_bot" not in servers
    assert not any(tool.startswith("mcp__record_progress__") for tool in allowed_tools)
    assert not any(tool.startswith("mcp__call_bot__") for tool in allowed_tools)


def test_prepare_skill_config_attaches_both_when_signals_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Goal present + multi-bot install → both MCPs attach."""
    from abyss.claude_runner import _prepare_skill_config

    _, session_dir = _prep(
        tmp_path,
        monkeypatch,
        goals=[{"id": "x", "title": "Smoke"}],
        bots=["alpha", "beta"],
    )

    _prepare_skill_config(str(session_dir), None)

    config = json.loads((session_dir / ".mcp.json").read_text())
    servers = config["mcpServers"]
    assert "record_progress" in servers
    assert "call_bot" in servers


def test_prepare_skill_config_propose_skill_always_attached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: propose_skill MUST stay always-on regardless of state.

    Phase 5 design: the bot needs the tool to exist before it has
    anything to propose. Gating it on "user already has skills" would
    create a chicken-and-egg dead-end.
    """
    from abyss.claude_runner import _prepare_skill_config

    _, session_dir = _prep(tmp_path, monkeypatch, goals=None, bots=["alpha"])

    _prepare_skill_config(str(session_dir), None)

    config = json.loads((session_dir / ".mcp.json").read_text())
    assert "propose_skill" in config["mcpServers"]
