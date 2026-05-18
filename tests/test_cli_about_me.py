"""CLI tests for ``abyss about-me``."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from abyss.cli import app


@pytest.fixture
def abyss_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
    return tmp_path


def test_init_creates_scaffold(abyss_home: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["about-me", "init"])
    assert result.exit_code == 0
    assert (abyss_home / "ABOUT_ME" / "INDEX.md").exists()
    assert (abyss_home / "ABOUT_ME" / "identity.md").exists()


def test_show_empty_emits_friendly_message(abyss_home: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["about-me", "show"])
    assert result.exit_code == 0
    assert "empty" in result.stdout.lower()


def test_show_after_init_renders_index(abyss_home: Path) -> None:
    runner = CliRunner()
    runner.invoke(app, ["about-me", "init"])
    result = runner.invoke(app, ["about-me", "show"])
    assert result.exit_code == 0
    assert "About Me" in result.stdout


def test_show_category(abyss_home: Path) -> None:
    from abyss.about_me import AboutEntry, upsert_entry

    upsert_entry("identity", AboutEntry(key="name", value="ash84"))

    runner = CliRunner()
    result = runner.invoke(app, ["about-me", "show", "identity"])
    assert result.exit_code == 0
    assert "ash84" in result.stdout
    assert "name" in result.stdout


def test_show_unknown_category(abyss_home: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["about-me", "show", "career"])
    assert result.exit_code == 1
    assert "Unknown category" in result.stdout


def test_list_empty(abyss_home: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["about-me", "list"])
    assert result.exit_code == 0
    assert "No ABOUT_ME entries" in result.stdout


def test_list_with_entries(abyss_home: Path) -> None:
    from abyss.about_me import AboutEntry, upsert_entry

    upsert_entry("identity", AboutEntry(key="name", value="ash84"))
    upsert_entry("preferences", AboutEntry(key="lang", value="ko"))

    runner = CliRunner()
    result = runner.invoke(app, ["about-me", "list"])
    assert result.exit_code == 0
    assert "name" in result.stdout
    assert "ash84" in result.stdout
    assert "Total: 2" in result.stdout


def test_migrate_without_global_memory_errors(abyss_home: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["about-me", "migrate", "--dry-run"])
    assert result.exit_code == 1
    assert "empty" in result.stdout.lower() or "missing" in result.stdout.lower()


def test_migrate_dry_run_uses_classifier(abyss_home: Path, monkeypatch) -> None:
    from abyss import about_me
    from abyss.session import save_global_memory

    save_global_memory("- I'm ash84, an engineer at Payhere.\n- I prefer Korean.")

    async def fake_classify(content: str, *, model: str = "haiku") -> dict:
        assert "ash84" in content
        return {
            "identity": [{"key": "name", "value": "ash84", "body": ""}],
            "preferences": [{"key": "lang", "value": "Korean", "body": ""}],
        }

    monkeypatch.setattr(about_me, "classify_global_memory", fake_classify)

    runner = CliRunner()
    result = runner.invoke(app, ["about-me", "migrate", "--dry-run"])
    assert result.exit_code == 0
    assert "identity" in result.stdout
    assert "ash84" in result.stdout
    # Dry-run did not write entry files.
    identity = abyss_home / "ABOUT_ME" / "identity.md"
    if identity.exists():
        assert "ash84" not in identity.read_text()


def test_migrate_writes_entries(abyss_home: Path, monkeypatch) -> None:
    from abyss import about_me
    from abyss.about_me import load_category
    from abyss.session import save_global_memory

    save_global_memory("- Engineer at Payhere.")

    async def fake_classify(content: str, *, model: str = "haiku") -> dict:
        return {
            "identity": [{"key": "job", "value": "engineer@Payhere"}],
        }

    monkeypatch.setattr(about_me, "classify_global_memory", fake_classify)

    runner = CliRunner()
    result = runner.invoke(app, ["about-me", "migrate", "--yes"])
    assert result.exit_code == 0
    entries = load_category("identity")
    assert any(entry.key == "job" for entry in entries)


def test_about_me_help_runs(abyss_home: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["about-me", "--help"])
    assert result.exit_code == 0
