"""CLI tests for ``abyss goals`` subcommands (Phase 6)."""

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


def test_show_empty(abyss_home: Path) -> None:
    result = CliRunner().invoke(app, ["goals", "show", "anne"])
    assert result.exit_code == 0
    assert "No goals" in result.stdout


def test_show_unknown_bot(abyss_home: Path) -> None:
    result = CliRunner().invoke(app, ["goals", "show", "ghost"])
    assert result.exit_code == 1


def test_add_and_show(abyss_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLUMNS", "200")
    add = CliRunner().invoke(app, ["goals", "add", "anne", "Ship blog", "--kpi", "PR merged"])
    assert add.exit_code == 0
    show = CliRunner().invoke(app, ["goals", "show", "anne"])
    assert "Ship blog" in show.stdout
    assert "PR merged" in show.stdout


def test_add_duplicate_id_fails(abyss_home: Path) -> None:
    CliRunner().invoke(app, ["goals", "add", "anne", "Ship blog"])
    result = CliRunner().invoke(app, ["goals", "add", "anne", "Ship blog"])
    assert result.exit_code == 1


def test_progress_logs_entry(abyss_home: Path) -> None:
    from abyss.goals import add_goal, get_goal

    g = add_goal("anne", "Ship blog")
    result = CliRunner().invoke(app, ["goals", "progress", "anne", g.id, "drafted plan"])
    assert result.exit_code == 0
    assert get_goal("anne", g.id).progress[-1].note == "drafted plan"


def test_progress_unknown_goal(abyss_home: Path) -> None:
    result = CliRunner().invoke(app, ["goals", "progress", "anne", "ghost", "note"])
    assert result.exit_code == 0
    assert "No goal" in result.stdout


def test_done_and_archive(abyss_home: Path) -> None:
    from abyss.goals import add_goal, get_goal

    g = add_goal("anne", "G")
    done = CliRunner().invoke(app, ["goals", "done", "anne", g.id])
    assert done.exit_code == 0
    assert get_goal("anne", g.id).status == "done"
    arch = CliRunner().invoke(app, ["goals", "archive", "anne", g.id])
    assert arch.exit_code == 0
    assert get_goal("anne", g.id).status == "archived"


def test_delete_goal(abyss_home: Path) -> None:
    from abyss.goals import add_goal, list_goals

    g = add_goal("anne", "G")
    result = CliRunner().invoke(app, ["goals", "delete", "anne", g.id])
    assert result.exit_code == 0
    assert list_goals("anne") == []


def test_schedule_registers_cron(abyss_home: Path) -> None:
    from abyss.cron import get_cron_job
    from abyss.goals import GOAL_DIGEST_JOB_NAME

    result = CliRunner().invoke(app, ["goals", "schedule", "anne"])
    assert result.exit_code == 0
    assert get_cron_job("anne", GOAL_DIGEST_JOB_NAME) is not None


def test_unschedule_removes_cron(abyss_home: Path) -> None:
    from abyss.cron import get_cron_job
    from abyss.goals import GOAL_DIGEST_JOB_NAME

    CliRunner().invoke(app, ["goals", "schedule", "anne"])
    result = CliRunner().invoke(app, ["goals", "unschedule", "anne"])
    assert result.exit_code == 0
    assert get_cron_job("anne", GOAL_DIGEST_JOB_NAME) is None
