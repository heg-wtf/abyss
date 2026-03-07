"""Tests for cclaw.config module."""

from pathlib import Path

import pytest

from cclaw.config import (
    add_bot_to_config,
    bot_directory,
    bot_exists,
    cclaw_home,
    default_config,
    detect_local_timezone,
    generate_claude_md,
    get_language,
    get_timezone,
    load_bot_config,
    load_config,
    remove_bot_from_config,
    save_bot_config,
    save_config,
)


@pytest.fixture
def temp_cclaw_home(tmp_path, monkeypatch):
    """Set CCLAW_HOME to a temporary directory."""
    home = tmp_path / ".cclaw"
    monkeypatch.setenv("CCLAW_HOME", str(home))
    return home


def test_cclaw_home_default(monkeypatch):
    """cclaw_home defaults to ~/.cclaw/."""
    monkeypatch.delenv("CCLAW_HOME", raising=False)
    assert cclaw_home() == Path.home() / ".cclaw"


def test_cclaw_home_override(monkeypatch, tmp_path):
    """cclaw_home can be overridden via CCLAW_HOME env var."""
    custom = tmp_path / "custom"
    monkeypatch.setenv("CCLAW_HOME", str(custom))
    assert cclaw_home() == custom


def test_load_config_missing(temp_cclaw_home):
    """load_config returns None when config.yaml doesn't exist."""
    assert load_config() is None


def test_save_and_load_config(temp_cclaw_home):
    """save_config creates config.yaml that load_config can read."""
    config = default_config()
    save_config(config)
    loaded = load_config()
    assert loaded is not None
    assert loaded["settings"]["log_level"] == "INFO"
    assert loaded["bots"] == []


def test_bot_directory(temp_cclaw_home):
    """bot_directory returns correct path."""
    assert bot_directory("test-bot") == temp_cclaw_home / "bots" / "test-bot"


def test_save_and_load_bot_config(temp_cclaw_home):
    """save_bot_config creates bot.yaml and CLAUDE.md."""
    bot_config = {
        "telegram_token": "fake-token",
        "telegram_username": "@test_bot",
        "telegram_botname": "Test Bot",
        "display_name": "My Bot",
        "role": "Test role",
        "goal": "Test goal",
        "personality": "Friendly helper",
        "allowed_users": [],
        "claude_args": [],
    }
    save_bot_config("test-bot", bot_config)

    loaded = load_bot_config("test-bot")
    assert loaded is not None
    assert loaded["telegram_token"] == "fake-token"
    assert loaded["personality"] == "Friendly helper"

    claude_md = (bot_directory("test-bot") / "CLAUDE.md").read_text()
    assert "# test-bot" in claude_md
    assert "Friendly helper" in claude_md
    assert "Test role" in claude_md
    assert "Test goal" in claude_md

    sessions_directory = bot_directory("test-bot") / "sessions"
    assert sessions_directory.exists()


def test_load_bot_config_missing(temp_cclaw_home):
    """load_bot_config returns None when bot doesn't exist."""
    assert load_bot_config("nonexistent") is None


def test_generate_claude_md(monkeypatch):
    """generate_claude_md produces expected markdown with config language."""
    monkeypatch.setattr("cclaw.config.load_config", lambda: {"language": "English"})
    result = generate_claude_md(
        "my-bot",
        "Careful and thorough",
        role="Infrastructure management",
        goal="Keep servers alive",
    )
    assert "# my-bot" in result
    assert "Careful and thorough" in result
    assert "Infrastructure management" in result
    assert "Keep servers alive" in result
    assert "Respond in English" in result


def test_generate_claude_md_without_goal(monkeypatch):
    """generate_claude_md omits Goal section when goal is empty."""
    monkeypatch.setattr("cclaw.config.load_config", lambda: {"language": "Korean"})
    result = generate_claude_md("my-bot", "Friendly", role="Helper")
    assert "## Goal" not in result


def test_add_and_remove_bot_from_config(temp_cclaw_home):
    """add_bot_to_config and remove_bot_from_config manage bot entries."""
    add_bot_to_config("bot-a")
    config = load_config()
    assert len(config["bots"]) == 1
    assert config["bots"][0]["name"] == "bot-a"

    add_bot_to_config("bot-a")
    config = load_config()
    assert len(config["bots"]) == 1

    add_bot_to_config("bot-b")
    config = load_config()
    assert len(config["bots"]) == 2

    remove_bot_from_config("bot-a")
    config = load_config()
    assert len(config["bots"]) == 1
    assert config["bots"][0]["name"] == "bot-b"


def test_bot_exists(temp_cclaw_home):
    """bot_exists checks config for existing bots."""
    assert not bot_exists("test-bot")
    add_bot_to_config("test-bot")
    assert bot_exists("test-bot")


def test_default_config():
    """default_config returns expected structure."""
    config = default_config()
    assert "bots" in config
    assert "settings" in config
    assert config["settings"]["command_timeout"] == 300
    assert config["timezone"] == "UTC"
    assert config["language"] == "Korean"


def test_valid_models():
    """VALID_MODELS and is_valid_model work correctly."""
    from cclaw.config import DEFAULT_MODEL, VALID_MODELS, is_valid_model

    assert DEFAULT_MODEL == "sonnet"
    assert "sonnet" in VALID_MODELS
    assert "opus" in VALID_MODELS
    assert "haiku" in VALID_MODELS

    assert is_valid_model("sonnet") is True
    assert is_valid_model("opus") is True
    assert is_valid_model("gpt4") is False
    assert is_valid_model("") is False


def test_save_bot_config_with_skills(temp_cclaw_home):
    """save_bot_config includes skill content in CLAUDE.md when skills are present."""
    # Create a skill first
    skill_dir = temp_cclaw_home / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# test-skill\n\nDo something useful.")

    bot_config = {
        "telegram_token": "fake-token",
        "personality": "Friendly",
        "role": "Helper",
        "goal": "",
        "allowed_users": [],
        "claude_args": [],
        "skills": ["test-skill"],
    }
    save_bot_config("skill-bot", bot_config)

    claude_md = (bot_directory("skill-bot") / "CLAUDE.md").read_text()
    assert "Available Skills" in claude_md
    assert "test-skill" in claude_md
    assert "Do something useful" in claude_md


def test_save_bot_config_without_skills(temp_cclaw_home):
    """save_bot_config without skills produces CLAUDE.md without skill section."""
    bot_config = {
        "telegram_token": "fake-token",
        "personality": "Friendly",
        "role": "Helper",
        "goal": "",
        "allowed_users": [],
        "claude_args": [],
    }
    save_bot_config("no-skill-bot", bot_config)

    claude_md = (bot_directory("no-skill-bot") / "CLAUDE.md").read_text()
    assert "Available Skills" not in claude_md
    assert "# no-skill-bot" in claude_md


# --- Timezone tests ---


def test_get_timezone_from_config(temp_cclaw_home):
    """get_timezone reads timezone from config.yaml."""
    config = default_config()
    config["timezone"] = "Asia/Seoul"
    save_config(config)
    assert get_timezone() == "Asia/Seoul"


def test_get_timezone_default_utc(temp_cclaw_home):
    """get_timezone returns UTC when no config exists."""
    assert get_timezone() == "UTC"


def test_get_timezone_missing_key(temp_cclaw_home):
    """get_timezone returns UTC when config has no timezone key."""
    save_config({"bots": [], "settings": {}})
    assert get_timezone() == "UTC"


def test_get_timezone_invalid_value(temp_cclaw_home):
    """get_timezone returns UTC when config has invalid timezone."""
    config = default_config()
    config["timezone"] = "Invalid/Timezone"
    save_config(config)
    assert get_timezone() == "UTC"


def test_detect_local_timezone_returns_string():
    """detect_local_timezone returns a non-empty string."""
    result = detect_local_timezone()
    assert isinstance(result, str)
    assert len(result) > 0


def test_detect_local_timezone_kst(monkeypatch):
    """detect_local_timezone maps KST to Asia/Seoul."""
    monkeypatch.setattr("cclaw.config.time", type("FakeTime", (), {"tzname": ("KST", "KDT")})())
    # Need to also make os.readlink fail so it doesn't try /etc/localtime
    monkeypatch.setattr("os.readlink", lambda _: (_ for _ in ()).throw(OSError()))
    result = detect_local_timezone()
    assert result == "Asia/Seoul"


# --- Language tests ---


def test_get_language_from_config(temp_cclaw_home):
    """get_language reads language from config.yaml."""
    config = default_config()
    config["language"] = "English"
    save_config(config)
    assert get_language() == "English"


def test_get_language_default_korean(temp_cclaw_home):
    """get_language returns Korean when no config exists."""
    assert get_language() == "Korean"


def test_get_language_missing_key(temp_cclaw_home):
    """get_language returns Korean when config has no language key."""
    save_config({"bots": [], "settings": {}})
    assert get_language() == "Korean"
