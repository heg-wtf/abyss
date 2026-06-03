"""CLI tests for ``abyss skills proposals`` (Phase 5)."""

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
    result = CliRunner().invoke(app, ["skills", "proposals", "show", "anne"])
    assert result.exit_code == 0
    assert "No proposals" in result.stdout


def test_show_unknown_bot(abyss_home: Path) -> None:
    result = CliRunner().invoke(app, ["skills", "proposals", "show", "ghost"])
    assert result.exit_code == 1


def test_show_renders_rows(abyss_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from abyss.skill_proposals import add_proposal

    # Force Rich to render at a wide column so URLs don't truncate.
    monkeypatch.setenv("COLUMNS", "200")

    add_proposal("anne", "https://github.com/owner/skill", "missing X")
    result = CliRunner().invoke(app, ["skills", "proposals", "show", "anne"])
    assert result.exit_code == 0
    assert "owner/skill" in result.stdout
    assert "missing X" in result.stdout


def test_show_filter_by_status(abyss_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from abyss.skill_proposals import add_proposal, update_status

    monkeypatch.setenv("COLUMNS", "200")
    a = add_proposal("anne", "https://github.com/x/a-skill", "r")
    add_proposal("anne", "https://github.com/x/b-skill", "r")
    update_status("anne", a.id, "approved")
    result = CliRunner().invoke(app, ["skills", "proposals", "show", "anne", "--status", "pending"])
    assert "b-skill" in result.stdout
    assert "a-skill" not in result.stdout


def test_approve_happy_path(abyss_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from abyss.skill_proposals import add_proposal, get_proposal

    p = add_proposal("anne", "https://github.com/owner/skill", "r")

    def fake_import(url: str, name: str | None = None) -> Path:
        path = abyss_home / "skills" / "skill"
        path.mkdir(parents=True, exist_ok=True)
        return path

    monkeypatch.setattr("abyss.skill.import_skill_from_github", fake_import)
    monkeypatch.setattr("abyss.skill.attach_skill_to_bot", lambda *_a, **_k: None)

    result = CliRunner().invoke(app, ["skills", "proposals", "approve", "anne", p.id])
    assert result.exit_code == 0, result.stdout
    assert "Approved" in result.stdout
    assert get_proposal("anne", p.id).status == "approved"


def test_approve_failure_propagates_exit(abyss_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from abyss.skill_proposals import add_proposal

    p = add_proposal("anne", "https://github.com/x/y", "r")
    monkeypatch.setattr(
        "abyss.skill.import_skill_from_github",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    result = CliRunner().invoke(app, ["skills", "proposals", "approve", "anne", p.id])
    assert result.exit_code == 1
    assert "import" in result.stdout
    assert "boom" in result.stdout


def test_reject_happy_path(abyss_home: Path) -> None:
    from abyss.skill_proposals import add_proposal, get_proposal

    p = add_proposal("anne", "https://github.com/x/y", "r")
    result = CliRunner().invoke(app, ["skills", "proposals", "reject", "anne", p.id])
    assert result.exit_code == 0
    assert "Rejected" in result.stdout
    assert get_proposal("anne", p.id).status == "rejected"


def test_reject_unknown_id(abyss_home: Path) -> None:
    result = CliRunner().invoke(app, ["skills", "proposals", "reject", "anne", "ghost"])
    assert result.exit_code == 0
    assert "No proposal" in result.stdout
