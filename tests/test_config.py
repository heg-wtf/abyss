"""Tests for abyss.config module."""

from pathlib import Path

import pytest

from abyss.config import (
    abyss_home,
    add_bot_to_config,
    apply_claude_code_env,
    bot_directory,
    bot_exists,
    default_claude_code_config,
    default_config,
    detect_local_timezone,
    generate_claude_md,
    get_claude_code_env,
    get_language,
    get_timezone,
    load_bot_config,
    load_config,
    remove_bot_from_config,
    save_bot_config,
    save_config,
)


@pytest.fixture
def temp_abyss_home(tmp_path, monkeypatch):
    """Set ABYSS_HOME to a temporary directory."""
    home = tmp_path / ".abyss"
    monkeypatch.setenv("ABYSS_HOME", str(home))
    return home


def test_abyss_home_default(monkeypatch):
    """abyss_home defaults to ~/.abyss/."""
    monkeypatch.delenv("ABYSS_HOME", raising=False)
    assert abyss_home() == Path.home() / ".abyss"


def test_abyss_home_override(monkeypatch, tmp_path):
    """abyss_home can be overridden via ABYSS_HOME env var."""
    custom = tmp_path / "custom"
    monkeypatch.setenv("ABYSS_HOME", str(custom))
    assert abyss_home() == custom


def test_load_config_missing(temp_abyss_home):
    """load_config returns None when config.yaml doesn't exist."""
    assert load_config() is None


def test_save_and_load_config(temp_abyss_home):
    """save_config creates config.yaml that load_config can read."""
    config = default_config()
    save_config(config)
    loaded = load_config()
    assert loaded is not None
    assert loaded["settings"]["log_level"] == "INFO"
    assert loaded["bots"] == []


def test_bot_directory(temp_abyss_home):
    """bot_directory returns correct path."""
    assert bot_directory("test-bot") == temp_abyss_home / "bots" / "test-bot"


def test_save_and_load_bot_config(temp_abyss_home):
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


def test_load_bot_config_missing(temp_abyss_home):
    """load_bot_config returns None when bot doesn't exist."""
    assert load_bot_config("nonexistent") is None


def test_generate_claude_md(monkeypatch):
    """generate_claude_md produces expected markdown with config language."""
    monkeypatch.setattr("abyss.config.load_config", lambda: {"language": "English"})
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
    monkeypatch.setattr("abyss.config.load_config", lambda: {"language": "Korean"})
    result = generate_claude_md("my-bot", "Friendly", role="Helper")
    assert "## Goal" not in result


def test_add_and_remove_bot_from_config(temp_abyss_home):
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


def test_bot_exists(temp_abyss_home):
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
    from abyss.config import DEFAULT_MODEL, VALID_MODELS, is_valid_model

    assert DEFAULT_MODEL == "sonnet"
    assert "sonnet" in VALID_MODELS
    assert "opus" in VALID_MODELS
    assert "haiku" in VALID_MODELS

    assert is_valid_model("sonnet") is True
    assert is_valid_model("opus") is True
    assert is_valid_model("gpt4") is False
    assert is_valid_model("") is False


def test_save_bot_config_with_skills(temp_abyss_home):
    """save_bot_config includes skill content in CLAUDE.md when skills are present."""
    # Create a skill first
    skill_dir = temp_abyss_home / "skills" / "test-skill"
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


def test_save_bot_config_without_skills(temp_abyss_home):
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


def test_get_timezone_from_config(temp_abyss_home):
    """get_timezone reads timezone from config.yaml."""
    config = default_config()
    config["timezone"] = "Asia/Seoul"
    save_config(config)
    assert get_timezone() == "Asia/Seoul"


def test_get_timezone_default_utc(temp_abyss_home):
    """get_timezone returns UTC when no config exists."""
    assert get_timezone() == "UTC"


def test_get_timezone_missing_key(temp_abyss_home):
    """get_timezone returns UTC when config has no timezone key."""
    save_config({"bots": [], "settings": {}})
    assert get_timezone() == "UTC"


def test_get_timezone_invalid_value(temp_abyss_home):
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
    monkeypatch.setattr("abyss.config.time", type("FakeTime", (), {"tzname": ("KST", "KDT")})())
    # Need to also make os.readlink fail so it doesn't try /etc/localtime
    monkeypatch.setattr("os.readlink", lambda _: (_ for _ in ()).throw(OSError()))
    result = detect_local_timezone()
    assert result == "Asia/Seoul"


# --- Language tests ---


def test_get_language_from_config(temp_abyss_home):
    """get_language reads language from config.yaml."""
    config = default_config()
    config["language"] = "English"
    save_config(config)
    assert get_language() == "English"


def test_get_language_default_korean(temp_abyss_home):
    """get_language returns Korean when no config exists."""
    assert get_language() == "Korean"


def test_get_language_missing_key(temp_abyss_home):
    """get_language returns Korean when config has no language key."""
    save_config({"bots": [], "settings": {}})
    assert get_language() == "Korean"


# --- Claude Code env tests ---


def test_get_claude_code_env_defaults_no_config(temp_abyss_home):
    """All toggles enabled by default when config.yaml is missing."""
    env = get_claude_code_env()
    assert env["AI_AGENT"] == "abyss"
    assert env["ENABLE_PROMPT_CACHING_1H"] == "1"
    assert env["CLAUDE_CODE_FORK_SUBAGENT"] == "1"
    assert env["MCP_CONNECTION_NONBLOCKING"] == "true"
    assert env["CLAUDE_CODE_HIDE_CWD"] == "1"


def test_get_claude_code_env_user_disable(temp_abyss_home):
    """User can disable individual toggles via config.yaml."""
    config = default_config()
    config["claude_code"] = {
        "prompt_caching_1h": False,
        "fork_subagent": True,
        "mcp_nonblocking": False,
        "hide_cwd": True,
    }
    save_config(config)

    env = get_claude_code_env()
    assert "ENABLE_PROMPT_CACHING_1H" not in env
    assert "MCP_CONNECTION_NONBLOCKING" not in env
    assert env["CLAUDE_CODE_FORK_SUBAGENT"] == "1"
    assert env["CLAUDE_CODE_HIDE_CWD"] == "1"
    # AI_AGENT is always on, not user-toggleable
    assert env["AI_AGENT"] == "abyss"


def test_get_claude_code_env_invalid_section_falls_back(temp_abyss_home):
    """Invalid claude_code section falls back to defaults."""
    save_config({"bots": [], "claude_code": "not-a-dict"})
    env = get_claude_code_env()
    assert env["ENABLE_PROMPT_CACHING_1H"] == "1"
    assert env["AI_AGENT"] == "abyss"


def test_default_claude_code_config_keys():
    """default_claude_code_config exposes all four toggles."""
    config = default_claude_code_config()
    assert set(config.keys()) == {
        "prompt_caching_1h",
        "fork_subagent",
        "mcp_nonblocking",
        "hide_cwd",
    }
    assert all(value is True for value in config.values())


def test_apply_claude_code_env_strips_host_value_on_disable(temp_abyss_home):
    """Disabled toggle removes the var even if host env exports it."""
    config = default_config()
    config["claude_code"] = {
        "prompt_caching_1h": False,
        "fork_subagent": True,
        "mcp_nonblocking": False,
        "hide_cwd": True,
    }
    save_config(config)

    base = {
        "PATH": "/usr/bin",
        "ENABLE_PROMPT_CACHING_1H": "1",  # leftover from user shell profile
        "MCP_CONNECTION_NONBLOCKING": "true",  # ditto
        "UNRELATED": "keep",
    }
    result = apply_claude_code_env(base)

    # Disabled toggles -> stripped, not preserved from host env
    assert "ENABLE_PROMPT_CACHING_1H" not in result
    assert "MCP_CONNECTION_NONBLOCKING" not in result
    # Enabled toggles -> set
    assert result["CLAUDE_CODE_FORK_SUBAGENT"] == "1"
    assert result["CLAUDE_CODE_HIDE_CWD"] == "1"
    # Always-on
    assert result["AI_AGENT"] == "abyss"
    # Unrelated host env preserved
    assert result["PATH"] == "/usr/bin"
    assert result["UNRELATED"] == "keep"


def test_apply_claude_code_env_does_not_mutate_input(temp_abyss_home):
    """apply_claude_code_env returns a new dict and leaves input intact."""
    base = {"PATH": "/usr/bin", "ENABLE_PROMPT_CACHING_1H": "stale"}
    snapshot = dict(base)
    apply_claude_code_env(base)
    assert base == snapshot


def test_apply_claude_code_env_overwrites_host_value_when_enabled(temp_abyss_home):
    """Enabled toggle overwrites whatever the host shell exported."""
    base = {"ENABLE_PROMPT_CACHING_1H": "stale-host-value"}
    result = apply_claude_code_env(base)
    assert result["ENABLE_PROMPT_CACHING_1H"] == "1"
