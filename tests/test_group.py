"""Tests for cclaw.group module."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cclaw.group import (
    bind_group,
    create_group,
    delete_group,
    find_group_by_chat_id,
    find_groups_for_bot,
    get_my_role,
    group_directory,
    list_groups,
    list_workspace_files,
    load_group_config,
    load_shared_conversation,
    log_to_shared_conversation,
    shared_workspace_path,
    unbind_group,
)


@pytest.fixture()
def temp_cclaw_home(tmp_path, monkeypatch):
    """Set CCLAW_HOME to a temporary directory with config."""
    home = tmp_path / ".cclaw"
    home.mkdir()
    monkeypatch.setenv("CCLAW_HOME", str(home))

    # Create config with registered bots
    config = {
        "bots": [
            {"name": "dev_lead", "path": str(home / "bots" / "dev_lead")},
            {"name": "coder", "path": str(home / "bots" / "coder")},
            {"name": "tester", "path": str(home / "bots" / "tester")},
            {"name": "researcher", "path": str(home / "bots" / "researcher")},
        ],
        "timezone": "Asia/Seoul",
        "language": "Korean",
    }
    with open(home / "config.yaml", "w") as file:
        yaml.dump(config, file, default_flow_style=False, allow_unicode=True)

    # Create bot directories with bot.yaml
    for bot_entry in config["bots"]:
        bot_directory = Path(bot_entry["path"])
        bot_directory.mkdir(parents=True, exist_ok=True)
        bot_config = {
            "telegram_token": f"fake-token-{bot_entry['name']}",
            "telegram_username": f"@{bot_entry['name']}_bot",
            "display_name": bot_entry["name"],
            "personality": f"Test personality for {bot_entry['name']}",
            "role": f"Test role for {bot_entry['name']}",
            "goal": f"Test goal for {bot_entry['name']}",
        }
        with open(bot_directory / "bot.yaml", "w") as file:
            yaml.dump(bot_config, file, default_flow_style=False, allow_unicode=True)

    return home


# --- create_group ---


def test_create_group(temp_cclaw_home):
    """create_group creates group.yaml and directories."""
    directory = create_group(
        name="dev_team",
        orchestrator="dev_lead",
        members=["coder", "tester"],
    )

    assert directory.exists()
    assert (directory / "group.yaml").exists()
    assert (directory / "conversation").is_dir()
    assert (directory / "workspace").is_dir()

    config = load_group_config("dev_team")
    assert config is not None
    assert config["name"] == "dev_team"
    assert config["orchestrator"] == "dev_lead"
    assert config["members"] == ["coder", "tester"]
    assert config["telegram_chat_id"] is None


def test_create_group_duplicate(temp_cclaw_home):
    """create_group raises ValueError for duplicate group name."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])

    with pytest.raises(ValueError, match="already exists"):
        create_group(name="dev_team", orchestrator="dev_lead", members=["tester"])


def test_create_group_invalid_orchestrator(temp_cclaw_home):
    """create_group raises ValueError for unregistered orchestrator."""
    with pytest.raises(ValueError, match="not registered"):
        create_group(name="dev_team", orchestrator="nonexistent", members=["coder"])


def test_create_group_invalid_member(temp_cclaw_home):
    """create_group raises ValueError for unregistered member."""
    with pytest.raises(ValueError, match="not registered"):
        create_group(name="dev_team", orchestrator="dev_lead", members=["coder", "nonexistent"])


def test_create_group_orchestrator_in_multiple_groups(temp_cclaw_home):
    """create_group allows orchestrator to be in multiple groups."""
    create_group(name="team_a", orchestrator="dev_lead", members=["coder"])
    create_group(name="team_b", orchestrator="dev_lead", members=["tester"])

    groups = find_groups_for_bot("dev_lead")
    assert len(groups) == 2


# --- load_group_config ---


def test_load_group_config(temp_cclaw_home):
    """load_group_config returns config dict."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    config = load_group_config("dev_team")
    assert config is not None
    assert config["name"] == "dev_team"


def test_load_group_config_nonexistent(temp_cclaw_home):
    """load_group_config returns None for nonexistent group."""
    config = load_group_config("nonexistent")
    assert config is None


# --- list_groups ---


def test_list_groups(temp_cclaw_home):
    """list_groups returns all group configs."""
    create_group(name="team_a", orchestrator="dev_lead", members=["coder"])
    create_group(name="team_b", orchestrator="coder", members=["tester"])

    groups = list_groups()
    assert len(groups) == 2
    names = {g["name"] for g in groups}
    assert names == {"team_a", "team_b"}


def test_list_groups_empty(temp_cclaw_home):
    """list_groups returns empty list when no groups exist."""
    groups = list_groups()
    assert groups == []


# --- delete_group ---


def test_delete_group(temp_cclaw_home):
    """delete_group removes the group directory."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    assert group_directory("dev_team").exists()

    delete_group("dev_team")
    assert not group_directory("dev_team").exists()


def test_delete_group_nonexistent(temp_cclaw_home):
    """delete_group raises ValueError for nonexistent group."""
    with pytest.raises(ValueError, match="does not exist"):
        delete_group("nonexistent")


# --- find_group_by_chat_id ---


def test_find_group_by_chat_id(temp_cclaw_home):
    """find_group_by_chat_id returns the correct group."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    bind_group("dev_team", -12345)

    result = find_group_by_chat_id(-12345)
    assert result is not None
    assert result["name"] == "dev_team"


def test_find_group_by_chat_id_unbound(temp_cclaw_home):
    """find_group_by_chat_id returns None for unbound groups."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])

    result = find_group_by_chat_id(-12345)
    assert result is None


def test_find_group_by_chat_id_multiple_groups(temp_cclaw_home):
    """find_group_by_chat_id returns correct group among multiple."""
    create_group(name="team_a", orchestrator="dev_lead", members=["coder"])
    create_group(name="team_b", orchestrator="coder", members=["tester"])
    bind_group("team_a", -11111)
    bind_group("team_b", -22222)

    result = find_group_by_chat_id(-22222)
    assert result is not None
    assert result["name"] == "team_b"


# --- bind_group / unbind_group ---


def test_bind_group(temp_cclaw_home):
    """bind_group records telegram_chat_id in group.yaml."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    bind_group("dev_team", -12345)

    config = load_group_config("dev_team")
    assert config is not None
    assert config["telegram_chat_id"] == -12345


def test_bind_group_overwrite(temp_cclaw_home):
    """bind_group overwrites existing chat_id."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    bind_group("dev_team", -12345)
    bind_group("dev_team", -99999)

    config = load_group_config("dev_team")
    assert config is not None
    assert config["telegram_chat_id"] == -99999


def test_bind_group_nonexistent(temp_cclaw_home):
    """bind_group raises ValueError for nonexistent group."""
    with pytest.raises(ValueError, match="does not exist"):
        bind_group("nonexistent", -12345)


def test_bind_group_chat_id_already_bound(temp_cclaw_home):
    """bind_group raises ValueError if chat_id is bound to another group."""
    create_group(name="team_a", orchestrator="dev_lead", members=["coder"])
    create_group(name="team_b", orchestrator="coder", members=["tester"])
    bind_group("team_a", -12345)

    with pytest.raises(ValueError, match="already bound"):
        bind_group("team_b", -12345)


def test_unbind_group(temp_cclaw_home):
    """unbind_group sets telegram_chat_id to None."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    bind_group("dev_team", -12345)
    unbind_group("dev_team")

    config = load_group_config("dev_team")
    assert config is not None
    assert config["telegram_chat_id"] is None


def test_unbind_group_nonexistent(temp_cclaw_home):
    """unbind_group raises ValueError for nonexistent group."""
    with pytest.raises(ValueError, match="does not exist"):
        unbind_group("nonexistent")


# --- get_my_role ---


def test_get_my_role_orchestrator(temp_cclaw_home):
    """get_my_role returns 'orchestrator' for the orchestrator bot."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    config = load_group_config("dev_team")
    assert config is not None
    assert get_my_role(config, "dev_lead") == "orchestrator"


def test_get_my_role_member(temp_cclaw_home):
    """get_my_role returns 'member' for a member bot."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    config = load_group_config("dev_team")
    assert config is not None
    assert get_my_role(config, "coder") == "member"


def test_get_my_role_not_in_group(temp_cclaw_home):
    """get_my_role returns None for a bot not in the group."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    config = load_group_config("dev_team")
    assert config is not None
    assert get_my_role(config, "researcher") is None


# --- find_groups_for_bot ---


def test_find_groups_for_bot_member(temp_cclaw_home):
    """find_groups_for_bot finds groups where bot is a member."""
    create_group(name="team_a", orchestrator="dev_lead", members=["coder", "tester"])
    create_group(name="team_b", orchestrator="researcher", members=["coder"])

    groups = find_groups_for_bot("coder")
    assert len(groups) == 2
    names = {g["name"] for g in groups}
    assert names == {"team_a", "team_b"}


def test_find_groups_for_bot_orchestrator(temp_cclaw_home):
    """find_groups_for_bot finds groups where bot is orchestrator."""
    create_group(name="team_a", orchestrator="dev_lead", members=["coder"])

    groups = find_groups_for_bot("dev_lead")
    assert len(groups) == 1
    assert groups[0]["name"] == "team_a"


def test_find_groups_for_bot_none(temp_cclaw_home):
    """find_groups_for_bot returns empty list for bot not in any group."""
    create_group(name="team_a", orchestrator="dev_lead", members=["coder"])

    groups = find_groups_for_bot("researcher")
    assert groups == []


# --- Shared Conversation Log ---


def test_log_to_shared_conversation(temp_cclaw_home):
    """log_to_shared_conversation writes to conversation file."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])

    log_to_shared_conversation("dev_team", "user", "Build a crawler")
    log_to_shared_conversation("dev_team", "@dev_lead_bot", "Mission accepted.")

    content = load_shared_conversation("dev_team")
    assert "user: Build a crawler" in content
    assert "@dev_lead_bot: Mission accepted." in content


def test_log_to_shared_conversation_append(temp_cclaw_home):
    """log_to_shared_conversation appends, does not overwrite."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])

    log_to_shared_conversation("dev_team", "user", "First message")
    log_to_shared_conversation("dev_team", "user", "Second message")

    content = load_shared_conversation("dev_team")
    assert "First message" in content
    assert "Second message" in content


def test_log_to_shared_conversation_sender_format(temp_cclaw_home):
    """log_to_shared_conversation formats sender correctly."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])

    log_to_shared_conversation("dev_team", "user", "Hello")
    log_to_shared_conversation("dev_team", "@coder_bot", "Done")

    content = load_shared_conversation("dev_team")
    lines = content.strip().split("\n")
    assert "] user: Hello" in lines[0]
    assert "] @coder_bot: Done" in lines[1]


def test_log_to_shared_conversation_date_file(temp_cclaw_home):
    """Messages on different dates are written to different files."""
    from datetime import datetime, timezone
    from unittest.mock import patch

    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])

    # Log a message with a mocked date (March 10)
    with patch("cclaw.group.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 3, 10, 14, 30, 0, tzinfo=timezone.utc)
        mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        log_to_shared_conversation("dev_team", "user", "Day one message")

    # Log a message with a different mocked date (March 11)
    with patch("cclaw.group.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 3, 11, 9, 0, 0, tzinfo=timezone.utc)
        mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        log_to_shared_conversation("dev_team", "user", "Day two message")

    conversation_dir = group_directory("dev_team") / "conversation"
    files = sorted(conversation_dir.glob("*.md"))
    assert len(files) == 2
    assert files[0].name == "260310.md"
    assert files[1].name == "260311.md"

    assert "Day one message" in files[0].read_text()
    assert "Day two message" in files[1].read_text()


def test_load_shared_conversation_empty(temp_cclaw_home):
    """load_shared_conversation returns empty string when no conversation exists."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])

    content = load_shared_conversation("dev_team")
    assert content == ""


def test_load_shared_conversation_max_lines(temp_cclaw_home):
    """load_shared_conversation respects max_lines limit."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])

    for i in range(20):
        log_to_shared_conversation("dev_team", "user", f"Message {i}")

    content = load_shared_conversation("dev_team", max_lines=5)
    lines = content.strip().split("\n")
    assert len(lines) == 5
    assert "Message 15" in lines[0]
    assert "Message 19" in lines[4]


# --- Shared Workspace ---


def test_shared_workspace_path(temp_cclaw_home):
    """shared_workspace_path returns and creates workspace directory."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    workspace = shared_workspace_path("dev_team")
    assert workspace.is_dir()


def test_list_workspace_files_empty(temp_cclaw_home):
    """list_workspace_files returns empty list for empty workspace."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    files = list_workspace_files("dev_team")
    assert files == []


def test_list_workspace_files(temp_cclaw_home):
    """list_workspace_files returns relative file paths."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])

    workspace = shared_workspace_path("dev_team")
    (workspace / "scraper.py").write_text("print('hello')")
    (workspace / "test_scraper.py").write_text("def test(): pass")

    files = list_workspace_files("dev_team")
    assert len(files) == 2
    assert "scraper.py" in files
    assert "test_scraper.py" in files
