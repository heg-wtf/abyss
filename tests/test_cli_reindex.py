"""Tests for the ``abyss reindex`` CLI command."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from abyss.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def configured_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / ".abyss"
    home.mkdir()
    monkeypatch.setenv("ABYSS_HOME", str(home))

    bot_path = home / "bots" / "alpha"
    sessions = bot_path / "sessions" / "chat_42"
    sessions.mkdir(parents=True)
    (sessions / "conversation-260425.md").write_text(
        "\n## user (2026-04-25 09:30:15 UTC)\n\nfirst message\n"
        "\n## assistant (2026-04-25 09:30:16 UTC)\n\nsecond message\n",
        encoding="utf-8",
    )

    config = {
        "bots": [{"name": "alpha", "path": str(bot_path)}],
        "timezone": "UTC",
        "language": "Korean",
    }
    with open(home / "config.yaml", "w") as file:
        yaml.dump(config, file)

    return home


@pytest.mark.enable_conversation_search
def test_reindex_bot(runner: CliRunner, configured_home: Path) -> None:
    result = runner.invoke(app, ["reindex", "--bot", "alpha"])
    assert result.exit_code == 0, result.stdout
    assert "indexed 2 message" in result.stdout
    assert (configured_home / "bots" / "alpha" / "conversation.db").exists()


@pytest.mark.enable_conversation_search
def test_reindex_all(runner: CliRunner, configured_home: Path) -> None:
    """``--all`` only walks the bot list now that the group surface
    is gone. Returning two indexed messages from the single
    configured bot is the new expected total."""
    result = runner.invoke(app, ["reindex", "--all"])
    assert result.exit_code == 0, result.stdout
    assert "alpha" in result.stdout
    assert "Reindex complete: 2" in result.stdout


@pytest.mark.enable_conversation_search
def test_reindex_no_args_errors(runner: CliRunner, configured_home: Path) -> None:
    result = runner.invoke(app, ["reindex"])
    assert result.exit_code != 0
    assert "Specify" in result.stdout


@pytest.mark.enable_conversation_search
def test_reindex_missing_bot(runner: CliRunner, configured_home: Path) -> None:
    result = runner.invoke(app, ["reindex", "--bot", "ghost"])
    assert result.exit_code == 0
    assert "Skip ghost" in result.stdout


def test_reindex_aborts_when_fts5_unavailable(runner: CliRunner, configured_home: Path) -> None:
    """Default conftest fixture stubs FTS5 to False — CLI should abort."""
    result = runner.invoke(app, ["reindex", "--all"])
    assert result.exit_code == 1
    assert "FTS5" in result.stdout
