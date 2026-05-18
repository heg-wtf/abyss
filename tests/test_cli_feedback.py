"""CLI tests for ``abyss feedback show``."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from abyss.cli import app


@pytest.fixture
def abyss_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / ".abyss"
    home.mkdir()
    monkeypatch.setenv("ABYSS_HOME", str(home))
    (home / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "bots": [{"name": "anne", "path": str(home / "bots" / "anne")}],
                "settings": {"language": "english", "timezone": "UTC"},
            }
        )
    )
    bot_dir = home / "bots" / "anne"
    bot_dir.mkdir(parents=True)
    bot_dir.joinpath("bot.yaml").write_text(
        yaml.safe_dump({"display_name": "Anne", "personality": "x", "role": "y"})
    )
    return home


def test_feedback_show_no_records(abyss_home: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["feedback", "show", "anne"])
    assert result.exit_code == 0
    assert "No feedback yet" in result.stdout


def test_feedback_show_unknown_bot(abyss_home: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["feedback", "show", "ghost"])
    assert result.exit_code == 1
    assert "not found" in result.stdout


def test_feedback_show_with_records(abyss_home: Path) -> None:
    from abyss.feedback import append_feedback

    for _ in range(4):
        append_feedback("anne", "chat_web_abc", f"turn-{_}", 1)
    append_feedback("anne", "chat_web_abc", "turn-meh", 2)

    runner = CliRunner()
    result = runner.invoke(app, ["feedback", "show", "anne"])
    assert result.exit_code == 0
    assert "Feedback for:" in result.stdout
    assert "anne" in result.stdout
    assert "Total:" in result.stdout
    assert "5" in result.stdout  # total
    assert "good" in result.stdout
    assert "meh" in result.stdout


def test_feedback_show_help_runs(abyss_home: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["feedback", "show", "--help"])
    assert result.exit_code == 0
