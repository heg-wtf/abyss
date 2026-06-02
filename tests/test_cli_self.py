"""CLI tests for ``abyss self`` subcommands (Phase 3 of co-evolution)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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


def test_self_show_empty(abyss_home: Path) -> None:
    result = CliRunner().invoke(app, ["self", "show", "anne"])
    assert result.exit_code == 0
    assert "empty" in result.stdout.lower()


def test_self_show_unknown_bot(abyss_home: Path) -> None:
    result = CliRunner().invoke(app, ["self", "show", "ghost"])
    assert result.exit_code == 1
    assert "not found" in result.stdout


def test_self_show_renders_markdown(abyss_home: Path) -> None:
    from abyss.self_reflection import save_self_md

    save_self_md("anne", "## Mistake patterns\n- talks too much\n")
    result = CliRunner().invoke(app, ["self", "show", "anne"])
    assert result.exit_code == 0
    assert "Mistake patterns" in result.stdout
    assert "talks too much" in result.stdout


def test_self_reflect_unknown_bot(abyss_home: Path) -> None:
    result = CliRunner().invoke(app, ["self", "reflect", "ghost"])
    assert result.exit_code == 1
    assert "not found" in result.stdout


def test_self_reflect_runs_and_writes(
    abyss_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_reflection(bot: str, cfg: dict[str, Any]) -> str:
        from abyss.self_reflection import save_self_md

        save_self_md(bot, "## Self update\n- be terse\n")
        return "## Self update\n- be terse\n"

    monkeypatch.setattr("abyss.self_reflection.run_reflection", fake_run_reflection)

    result = CliRunner().invoke(app, ["self", "reflect", "anne"])
    assert result.exit_code == 0
    assert "updated" in result.stdout.lower()
    from abyss.self_reflection import load_self_md

    assert "be terse" in load_self_md("anne")


def test_self_schedule_registers_cron_with_default(abyss_home: Path) -> None:
    from abyss.cron import get_cron_job
    from abyss.self_reflection import DEFAULT_REFLECTION_CRON, REFLECTION_JOB_NAME

    result = CliRunner().invoke(app, ["self", "schedule", "anne"])
    assert result.exit_code == 0
    assert "Scheduled" in result.stdout
    job = get_cron_job("anne", REFLECTION_JOB_NAME)
    assert job is not None
    assert job["schedule"] == DEFAULT_REFLECTION_CRON
    assert job["enabled"] is True


def test_self_schedule_custom_cron(abyss_home: Path) -> None:
    from abyss.cron import get_cron_job
    from abyss.self_reflection import REFLECTION_JOB_NAME

    result = CliRunner().invoke(app, ["self", "schedule", "anne", "--cron", "*/5 * * * *"])
    assert result.exit_code == 0
    job = get_cron_job("anne", REFLECTION_JOB_NAME)
    assert job is not None
    assert job["schedule"] == "*/5 * * * *"


def test_self_schedule_unknown_bot(abyss_home: Path) -> None:
    result = CliRunner().invoke(app, ["self", "schedule", "ghost"])
    assert result.exit_code == 1
    assert "not found" in result.stdout


def test_self_schedule_duplicate_guard(abyss_home: Path) -> None:
    runner = CliRunner()
    first = runner.invoke(app, ["self", "schedule", "anne"])
    assert first.exit_code == 0
    second = runner.invoke(app, ["self", "schedule", "anne"])
    assert second.exit_code == 1
    assert "already scheduled" in second.stdout


def test_self_unschedule_removes_cron(abyss_home: Path) -> None:
    from abyss.cron import get_cron_job
    from abyss.self_reflection import REFLECTION_JOB_NAME

    runner = CliRunner()
    runner.invoke(app, ["self", "schedule", "anne"])
    result = runner.invoke(app, ["self", "unschedule", "anne"])
    assert result.exit_code == 0
    assert "Removed" in result.stdout
    assert get_cron_job("anne", REFLECTION_JOB_NAME) is None


def test_self_unschedule_no_job_warns(abyss_home: Path) -> None:
    result = CliRunner().invoke(app, ["self", "unschedule", "anne"])
    assert result.exit_code == 0
    assert "No" in result.stdout


def test_self_unschedule_unknown_bot(abyss_home: Path) -> None:
    result = CliRunner().invoke(app, ["self", "unschedule", "ghost"])
    assert result.exit_code == 1
    assert "not found" in result.stdout
