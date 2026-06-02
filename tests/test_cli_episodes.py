"""CLI tests for ``abyss episodes`` and ``abyss facts`` subcommands (Phase 4)."""

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


# --- episodes show ------------------------------------------------------------


def test_episodes_show_empty(abyss_home: Path) -> None:
    result = CliRunner().invoke(app, ["episodes", "show", "anne"])
    assert result.exit_code == 0
    assert "No episodes" in result.stdout


def test_episodes_show_unknown_bot(abyss_home: Path) -> None:
    result = CliRunner().invoke(app, ["episodes", "show", "ghost"])
    assert result.exit_code == 1
    assert "not found" in result.stdout


def test_episodes_show_renders_table(abyss_home: Path) -> None:
    from abyss.episodes import Episode, append_episode

    append_episode(
        "anne",
        Episode(
            ts="2026-06-01T00:00:00+00:00",
            date="2026-06-01",
            kind="decision",
            summary="ship phase 4",
            source_turn="conversation-260601.md",
        ),
    )
    result = CliRunner().invoke(app, ["episodes", "show", "anne"])
    assert result.exit_code == 0
    assert "ship phase 4" in result.stdout
    assert "decision" in result.stdout


def test_episodes_show_kind_filter(abyss_home: Path) -> None:
    from abyss.episodes import Episode, append_episode

    for kind, summary in [
        ("decision", "the decision row"),
        ("fact", "the fact row"),
    ]:
        append_episode(
            "anne",
            Episode(
                ts="2026-06-01T00:00:00+00:00",
                date="2026-06-01",
                kind=kind,
                summary=summary,
            ),
        )
    result = CliRunner().invoke(app, ["episodes", "show", "anne", "--kind", "decision"])
    assert "the decision row" in result.stdout
    assert "the fact row" not in result.stdout


# --- episodes extract ---------------------------------------------------------


def test_episodes_extract_unknown_bot(abyss_home: Path) -> None:
    result = CliRunner().invoke(app, ["episodes", "extract", "ghost"])
    assert result.exit_code == 1


def test_episodes_extract_invokes_extractor(
    abyss_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: dict[str, Any] = {}

    async def fake_extract(bot: str, cfg: dict[str, Any], *, yymmdd: str | None = None):
        calls["bot"] = bot
        calls["yymmdd"] = yymmdd
        return [0, 1], [10]

    monkeypatch.setattr("abyss.episodes.extract_yesterday", fake_extract)
    result = CliRunner().invoke(app, ["episodes", "extract", "anne", "--date", "260601"])
    assert result.exit_code == 0, result.stdout
    assert calls == {"bot": "anne", "yymmdd": "260601"}
    assert "2 episodes" in result.stdout
    assert "1 facts" in result.stdout


# --- episodes schedule / unschedule -------------------------------------------


def test_episodes_schedule_registers_cron(abyss_home: Path) -> None:
    from abyss.cron import get_cron_job
    from abyss.episodes import EPISODE_EXTRACT_JOB_NAME

    result = CliRunner().invoke(app, ["episodes", "schedule", "anne"])
    assert result.exit_code == 0
    assert get_cron_job("anne", EPISODE_EXTRACT_JOB_NAME) is not None


def test_episodes_schedule_rejects_duplicate(abyss_home: Path) -> None:
    CliRunner().invoke(app, ["episodes", "schedule", "anne"])
    result = CliRunner().invoke(app, ["episodes", "schedule", "anne"])
    assert result.exit_code == 1
    assert "already scheduled" in result.stdout


def test_episodes_unschedule_removes_cron(abyss_home: Path) -> None:
    from abyss.cron import get_cron_job
    from abyss.episodes import EPISODE_EXTRACT_JOB_NAME

    CliRunner().invoke(app, ["episodes", "schedule", "anne"])
    result = CliRunner().invoke(app, ["episodes", "unschedule", "anne"])
    assert result.exit_code == 0
    assert get_cron_job("anne", EPISODE_EXTRACT_JOB_NAME) is None


def test_episodes_unschedule_no_op(abyss_home: Path) -> None:
    result = CliRunner().invoke(app, ["episodes", "unschedule", "anne"])
    assert result.exit_code == 0
    assert "No '" in result.stdout


# --- facts show ---------------------------------------------------------------


def test_facts_show_empty(abyss_home: Path) -> None:
    result = CliRunner().invoke(app, ["facts", "show", "anne"])
    assert result.exit_code == 0
    assert "No facts" in result.stdout


def test_facts_show_renders_table(abyss_home: Path) -> None:
    from abyss.episodes import Fact, upsert_fact

    upsert_fact("anne", Fact(subject="release", claim="shipped", confidence=0.9))
    result = CliRunner().invoke(app, ["facts", "show", "anne"])
    assert result.exit_code == 0
    assert "release" in result.stdout
    assert "shipped" in result.stdout


def test_facts_show_include_retracted(abyss_home: Path) -> None:
    from abyss.episodes import Fact, retract_fact, upsert_fact

    fact_id = upsert_fact("anne", Fact(subject="x", claim="y", confidence=0.9))
    retract_fact("anne", fact_id)
    result_default = CliRunner().invoke(app, ["facts", "show", "anne"])
    assert "No facts" in result_default.stdout
    result_all = CliRunner().invoke(app, ["facts", "show", "anne", "--include-retracted"])
    assert "retracted" in result_all.stdout


# --- facts retract ------------------------------------------------------------


def test_facts_retract_happy_path(abyss_home: Path) -> None:
    from abyss.episodes import Fact, query_facts, upsert_fact

    fact_id = upsert_fact("anne", Fact(subject="x", claim="y", confidence=0.9))
    result = CliRunner().invoke(app, ["facts", "retract", "anne", str(fact_id)])
    assert result.exit_code == 0
    assert "Retracted" in result.stdout
    rows = query_facts("anne", statuses=("retracted",))
    assert len(rows) == 1


def test_facts_retract_unknown_id(abyss_home: Path) -> None:
    result = CliRunner().invoke(app, ["facts", "retract", "anne", "999"])
    assert result.exit_code == 0
    assert "No fact 999" in result.stdout


def test_facts_retract_unknown_bot(abyss_home: Path) -> None:
    result = CliRunner().invoke(app, ["facts", "retract", "ghost", "1"])
    assert result.exit_code == 1
