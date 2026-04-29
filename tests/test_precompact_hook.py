"""Tests for the PreCompact hook entry point.

The hook script must:
1. exit 0 silently when ``AI_AGENT`` is not ``abyss`` (defensive guard
   against accidental fires from a stray ``~/.claude/settings.json``).
2. exit 0 when stdin is empty / malformed JSON / lacks a ``cwd``.
3. resolve the bot name from the payload's ``cwd`` and trigger
   ``run_compact`` for that bot.
4. swallow exceptions raised by ``run_compact`` so a failing compact
   never blocks the host's transcript compaction.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from abyss.hooks import precompact_hook


@pytest.fixture
def abyss_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mark the subprocess as launched by abyss."""
    monkeypatch.setenv("AI_AGENT", "abyss")


def _stdin_with(payload: dict) -> io.StringIO:
    return io.StringIO(json.dumps(payload))


# ─── Guard: not invoked by abyss ─────────────────────────────────────────


def test_main_no_op_when_ai_agent_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_AGENT", raising=False)
    # Should never call run_compact; absence of patch means a real call
    # would hit the network. The exit code alone is the contract.
    assert precompact_hook.main(stdin=_stdin_with({"cwd": "/tmp"})) == 0


def test_main_no_op_when_ai_agent_other(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_AGENT", "claude-code")
    assert precompact_hook.main(stdin=_stdin_with({"cwd": "/tmp"})) == 0


# ─── Stdin handling ──────────────────────────────────────────────────────


def test_main_handles_empty_stdin(abyss_env: None) -> None:
    """Empty stdin -> exit 0 without invoking run_compact."""
    with patch("abyss.token_compact.run_compact") as run_compact:
        assert precompact_hook.main(stdin=io.StringIO("")) == 0
    run_compact.assert_not_called()


def test_main_handles_invalid_json(abyss_env: None) -> None:
    """Malformed JSON -> exit 0 without invoking run_compact."""
    with patch("abyss.token_compact.run_compact") as run_compact:
        assert precompact_hook.main(stdin=io.StringIO("{not json")) == 0
    run_compact.assert_not_called()


def test_main_handles_non_object_payload(abyss_env: None) -> None:
    """Non-object JSON payload -> exit 0 without invoking run_compact."""
    with patch("abyss.token_compact.run_compact") as run_compact:
        assert precompact_hook.main(stdin=io.StringIO("[]")) == 0
    run_compact.assert_not_called()


def test_main_skips_when_payload_omits_cwd(
    abyss_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Even if cwd is inherited from the bot session dir, an invalid
    payload (missing ``cwd``) must NOT trigger compaction. Codex P2.
    """
    # Simulate the hook process inheriting a bot session as its cwd.
    session = tmp_path / "bots" / "alpha" / "sessions" / "chat_42"
    session.mkdir(parents=True)
    monkeypatch.chdir(session)

    with patch("abyss.token_compact.run_compact") as run_compact:
        # Payload exists but lacks ``cwd``.
        assert precompact_hook.main(stdin=_stdin_with({"session_id": "x"})) == 0
    run_compact.assert_not_called()


# ─── cwd resolution ──────────────────────────────────────────────────────


def test_resolve_bot_name_from_dm_session(tmp_path: Path) -> None:
    session = tmp_path / "bots" / "alpha" / "sessions" / "chat_42"
    session.mkdir(parents=True)
    assert precompact_hook._resolve_bot_name_from_cwd(str(session)) == "alpha"


def test_resolve_bot_name_from_heartbeat(tmp_path: Path) -> None:
    heartbeat = tmp_path / "bots" / "beta" / "heartbeat_sessions"
    heartbeat.mkdir(parents=True)
    assert precompact_hook._resolve_bot_name_from_cwd(str(heartbeat)) == "beta"


def test_resolve_bot_name_from_cron_job(tmp_path: Path) -> None:
    cron = tmp_path / "bots" / "gamma" / "cron_sessions" / "morning"
    cron.mkdir(parents=True)
    assert precompact_hook._resolve_bot_name_from_cwd(str(cron)) == "gamma"


def test_resolve_bot_name_returns_none_when_outside_bots(tmp_path: Path) -> None:
    other = tmp_path / "elsewhere"
    other.mkdir()
    assert precompact_hook._resolve_bot_name_from_cwd(str(other)) is None


def test_main_no_op_when_cwd_outside_bots(abyss_env: None, tmp_path: Path) -> None:
    payload = {"cwd": str(tmp_path)}
    with patch("abyss.token_compact.run_compact") as run_compact:
        result = precompact_hook.main(stdin=_stdin_with(payload))
    assert result == 0
    run_compact.assert_not_called()


# ─── Happy path: invokes run_compact ─────────────────────────────────────


def test_main_invokes_run_compact_with_resolved_bot(abyss_env: None, tmp_path: Path) -> None:
    session = tmp_path / "bots" / "alpha" / "sessions" / "chat_42"
    session.mkdir(parents=True)
    payload = {"cwd": str(session)}

    fake_run_compact = AsyncMock(return_value=[])
    with (
        patch("abyss.token_compact.run_compact", fake_run_compact),
        patch("abyss.token_compact.save_compact_results") as save,
    ):
        result = precompact_hook.main(stdin=_stdin_with(payload))

    assert result == 0
    fake_run_compact.assert_awaited_once_with("alpha")
    save.assert_called_once()


# ─── Failure path: swallow exceptions ────────────────────────────────────


def test_main_swallows_run_compact_exception(abyss_env: None, tmp_path: Path) -> None:
    session = tmp_path / "bots" / "alpha" / "sessions" / "chat_42"
    session.mkdir(parents=True)
    payload = {"cwd": str(session)}

    failing = AsyncMock(side_effect=RuntimeError("compact boom"))
    with patch("abyss.token_compact.run_compact", failing):
        result = precompact_hook.main(stdin=_stdin_with(payload))

    # Exit 0 even though run_compact raised. The host transcript compact
    # must not be blocked by abyss errors.
    assert result == 0
