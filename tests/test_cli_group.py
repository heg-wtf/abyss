"""Tests for cclaw CLI group subcommands."""

from __future__ import annotations

import pytest
import yaml
from typer.testing import CliRunner

from cclaw.cli import app
from cclaw.group import bind_group, load_group_config

runner = CliRunner()


@pytest.fixture()
def temp_cclaw_home(tmp_path, monkeypatch):
    """Set CCLAW_HOME to a temporary directory with registered bots."""
    home = tmp_path / ".cclaw"
    home.mkdir()
    monkeypatch.setenv("CCLAW_HOME", str(home))

    config = {
        "bots": [
            {"name": "dev_lead", "path": str(home / "bots" / "dev_lead")},
            {"name": "coder", "path": str(home / "bots" / "coder")},
            {"name": "tester", "path": str(home / "bots" / "tester")},
        ],
        "timezone": "Asia/Seoul",
        "language": "Korean",
    }
    with open(home / "config.yaml", "w") as file:
        yaml.dump(config, file, default_flow_style=False, allow_unicode=True)

    bots = [
        {
            "name": "dev_lead",
            "telegram_token": "fake-token-dev-lead",
            "telegram_username": "@dev_lead_bot",
            "display_name": "Dev Lead",
            "personality": "Technical leader",
            "role": "Team lead",
            "goal": "Manage team",
        },
        {
            "name": "coder",
            "telegram_token": "fake-token-coder",
            "telegram_username": "@coder_bot",
            "display_name": "Coder",
            "personality": "Senior developer",
            "role": "Write code",
            "goal": "Clean code",
        },
        {
            "name": "tester",
            "telegram_token": "fake-token-tester",
            "telegram_username": "@tester_bot",
            "display_name": "Tester",
            "personality": "QA engineer",
            "role": "Write tests",
            "goal": "Bug-free code",
        },
    ]
    for bot in bots:
        bot_directory = home / "bots" / bot["name"]
        bot_directory.mkdir(parents=True, exist_ok=True)
        bot_config = {k: v for k, v in bot.items() if k != "name"}
        with open(bot_directory / "bot.yaml", "w") as file:
            yaml.dump(bot_config, file, default_flow_style=False, allow_unicode=True)

    return home


# --- cclaw group create ---


def test_group_create(temp_cclaw_home):
    """cclaw group create creates group and shows confirmation."""
    result = runner.invoke(
        app, ["group", "create", "dev_team", "-o", "dev_lead", "-m", "coder,tester"]
    )

    assert result.exit_code == 0
    assert "dev_team" in result.output
    assert "created" in result.output
    assert "dev_lead" in result.output
    assert "coder" in result.output

    config = load_group_config("dev_team")
    assert config is not None
    assert config["orchestrator"] == "dev_lead"
    assert config["members"] == ["coder", "tester"]


def test_group_create_nonexistent_orchestrator(temp_cclaw_home):
    """cclaw group create with nonexistent orchestrator shows error."""
    result = runner.invoke(app, ["group", "create", "dev_team", "-o", "nonexistent", "-m", "coder"])

    assert result.exit_code == 1
    assert "not registered" in result.output


def test_group_create_nonexistent_member(temp_cclaw_home):
    """cclaw group create with nonexistent member shows error."""
    result = runner.invoke(
        app, ["group", "create", "dev_team", "-o", "dev_lead", "-m", "coder,nonexistent"]
    )

    assert result.exit_code == 1
    assert "not registered" in result.output


def test_group_create_duplicate(temp_cclaw_home):
    """cclaw group create with duplicate name shows error."""
    runner.invoke(app, ["group", "create", "dev_team", "-o", "dev_lead", "-m", "coder"])
    result = runner.invoke(app, ["group", "create", "dev_team", "-o", "dev_lead", "-m", "tester"])

    assert result.exit_code == 1
    assert "already exists" in result.output


# --- cclaw group list ---


def test_group_list_empty(temp_cclaw_home):
    """cclaw group list with no groups shows message."""
    result = runner.invoke(app, ["group", "list"])

    assert result.exit_code == 0
    assert "No groups" in result.output


def test_group_list_with_groups(temp_cclaw_home):
    """cclaw group list shows all groups."""
    runner.invoke(app, ["group", "create", "team_a", "-o", "dev_lead", "-m", "coder"])
    runner.invoke(app, ["group", "create", "team_b", "-o", "coder", "-m", "tester"])

    result = runner.invoke(app, ["group", "list"])

    assert result.exit_code == 0
    assert "team_a" in result.output
    assert "team_b" in result.output
    assert "dev_lead" in result.output


def test_group_list_binding_status(temp_cclaw_home):
    """cclaw group list shows bound/not bound status."""
    runner.invoke(app, ["group", "create", "team_a", "-o", "dev_lead", "-m", "coder"])
    runner.invoke(app, ["group", "create", "team_b", "-o", "coder", "-m", "tester"])
    bind_group("team_a", -12345)

    result = runner.invoke(app, ["group", "list"])

    assert result.exit_code == 0
    assert "bound" in result.output
    assert "not bound" in result.output


# --- cclaw group show ---


def test_group_show(temp_cclaw_home):
    """cclaw group show displays group details."""
    runner.invoke(app, ["group", "create", "dev_team", "-o", "dev_lead", "-m", "coder,tester"])

    result = runner.invoke(app, ["group", "show", "dev_team"])

    assert result.exit_code == 0
    assert "dev_team" in result.output
    assert "dev_lead" in result.output
    assert "coder" in result.output
    assert "tester" in result.output
    assert "0 files" in result.output


def test_group_show_nonexistent(temp_cclaw_home):
    """cclaw group show for nonexistent group shows error."""
    result = runner.invoke(app, ["group", "show", "nonexistent"])

    assert result.exit_code == 1
    assert "not found" in result.output


# --- cclaw group delete ---


def test_group_delete(temp_cclaw_home):
    """cclaw group delete removes group after confirmation."""
    runner.invoke(app, ["group", "create", "dev_team", "-o", "dev_lead", "-m", "coder"])

    result = runner.invoke(app, ["group", "delete", "dev_team"], input="y\n")

    assert result.exit_code == 0
    assert "deleted" in result.output

    config = load_group_config("dev_team")
    assert config is None


def test_group_delete_nonexistent(temp_cclaw_home):
    """cclaw group delete for nonexistent group shows error."""
    result = runner.invoke(app, ["group", "delete", "nonexistent"])

    assert result.exit_code == 1
    assert "not found" in result.output
