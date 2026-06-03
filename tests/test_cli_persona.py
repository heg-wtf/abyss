"""CLI tests for ``abyss persona`` subcommands (Phase 8.0)."""

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
        yaml.safe_dump({"display_name": "Anne", "personality": "p", "role": "r"})
    )
    return home


def test_show_empty(abyss_home: Path) -> None:
    result = CliRunner().invoke(app, ["persona", "show", "anne"])
    assert result.exit_code == 0
    assert "No persona snapshots" in result.stdout


def test_show_unknown_bot(abyss_home: Path) -> None:
    result = CliRunner().invoke(app, ["persona", "show", "ghost"])
    assert result.exit_code == 1


def test_snapshot_creates_row(abyss_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("abyss.persona_drift._compose_for_bot", lambda _bot: "## A\nbody\n")
    result = CliRunner().invoke(app, ["persona", "snapshot", "anne"])
    assert result.exit_code == 0
    assert "Snapshot taken" in result.stdout


def test_drift_no_history(abyss_home: Path) -> None:
    result = CliRunner().invoke(app, ["persona", "drift", "anne"])
    assert result.exit_code == 0
    assert "Not enough snapshots" in result.stdout


def test_drift_reports_shrinkage(abyss_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from abyss.persona_drift import take_snapshot

    monkeypatch.setattr(
        "abyss.persona_drift._compose_for_bot",
        lambda _bot: "## A\n" + ("big " * 200) + "\n",
    )
    monkeypatch.setattr("abyss.persona_drift._iso_now", lambda: "2026-05-27T00:00:00+00:00")
    take_snapshot("anne", event="manual")
    monkeypatch.setattr("abyss.persona_drift._iso_now", lambda: "2026-06-03T00:00:00+00:00")
    monkeypatch.setattr("abyss.persona_drift._compose_for_bot", lambda _bot: "## A\ntiny\n")
    take_snapshot("anne", event="manual")
    result = CliRunner().invoke(app, ["persona", "drift", "anne", "--window", "7"])
    assert result.exit_code == 0
    assert "shrinkage alert" in result.stdout


def test_schedule_and_unschedule(abyss_home: Path) -> None:
    from abyss.cron import get_cron_job
    from abyss.persona_drift import PERSONA_DAILY_JOB_NAME, PERSONA_DIGEST_JOB_NAME

    sched = CliRunner().invoke(app, ["persona", "schedule", "anne"])
    assert sched.exit_code == 0
    assert get_cron_job("anne", PERSONA_DAILY_JOB_NAME) is not None
    assert get_cron_job("anne", PERSONA_DIGEST_JOB_NAME) is not None

    unsched = CliRunner().invoke(app, ["persona", "unschedule", "anne"])
    assert unsched.exit_code == 0
    assert get_cron_job("anne", PERSONA_DAILY_JOB_NAME) is None
    assert get_cron_job("anne", PERSONA_DIGEST_JOB_NAME) is None


def test_unschedule_unknown_bot(abyss_home: Path) -> None:
    result = CliRunner().invoke(app, ["persona", "unschedule", "ghost"])
    assert result.exit_code == 1
