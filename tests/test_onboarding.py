"""Tests for cclaw.onboarding module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cclaw.onboarding import (
    EnvironmentCheckResult,
    _is_daemon_running,
    check_claude_code,
    check_node,
    check_python,
    create_bot,
    prompt_language,
    prompt_timezone,
    run_environment_checks,
    save_init_config,
    validate_telegram_token,
)


def test_check_python():
    """check_python should always succeed."""
    result = check_python()
    assert result.available is True
    assert result.name == "Python"
    assert result.version


def test_check_node_installed():
    """check_node returns available=True when node is found."""
    with patch("cclaw.onboarding.shutil.which", return_value="/usr/local/bin/node"):
        with patch("cclaw.onboarding.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="v20.11.0\n", stderr="")
            result = check_node()
            assert result.available is True
            assert "20" in result.version


def test_check_node_missing():
    """check_node returns available=False when node is not found."""
    with patch("cclaw.onboarding.shutil.which", return_value=None):
        result = check_node()
        assert result.available is False


def test_check_claude_code_installed():
    """check_claude_code returns available=True when claude is found."""
    with patch("cclaw.onboarding.shutil.which", return_value="/usr/local/bin/claude"):
        with patch("cclaw.onboarding.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="1.0.23\n", stderr="")
            result = check_claude_code()
            assert result.available is True
            assert "1.0.23" in result.version


def test_check_claude_code_missing():
    """check_claude_code returns available=False when claude is not found."""
    with patch("cclaw.onboarding.shutil.which", return_value=None):
        result = check_claude_code()
        assert result.available is False
        assert "npm install" in result.message


def test_run_environment_checks():
    """run_environment_checks returns a list of 3 checks."""
    with patch("cclaw.onboarding.shutil.which", return_value="/usr/bin/fake"):
        with patch("cclaw.onboarding.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="v1.0.0\n", stderr="")
            checks = run_environment_checks()
            assert len(checks) == 3
            assert all(isinstance(c, EnvironmentCheckResult) for c in checks)


@pytest.mark.asyncio
async def test_validate_telegram_token_valid():
    """validate_telegram_token returns bot info for valid token."""
    mock_bot_info = MagicMock()
    mock_bot_info.username = "test_bot"
    mock_bot_info.first_name = "Test Bot"

    with patch("telegram.Bot") as mock_bot_class:
        mock_bot = MagicMock()
        mock_bot.get_me = AsyncMock(return_value=mock_bot_info)
        mock_bot_class.return_value = mock_bot

        result = await validate_telegram_token("valid-token")
        assert result is not None
        assert result["username"] == "@test_bot"
        assert result["botname"] == "Test Bot"


@pytest.mark.asyncio
async def test_validate_telegram_token_invalid():
    """validate_telegram_token returns None for invalid token."""
    with patch("telegram.Bot") as mock_bot_class:
        mock_bot = MagicMock()
        mock_bot.get_me = AsyncMock(side_effect=Exception("Invalid token"))
        mock_bot_class.return_value = mock_bot

        result = await validate_telegram_token("invalid-token")
        assert result is None


def test_create_bot(tmp_path, monkeypatch):
    """create_bot creates all necessary files."""
    monkeypatch.setenv("CCLAW_HOME", str(tmp_path / ".cclaw"))

    token = "123456:ABCDEF"
    bot_info = {"username": "@test_bot", "botname": "Test Bot"}
    profile = {
        "name": "test-bot",
        "display_name": "My Test Bot",
        "personality": "Helpful assistant",
        "role": "General help",
        "goal": "Make life easier",
    }

    create_bot(token, bot_info, profile)

    bot_directory = tmp_path / ".cclaw" / "bots" / "test-bot"
    assert (bot_directory / "bot.yaml").exists()
    assert (bot_directory / "CLAUDE.md").exists()
    assert (bot_directory / "sessions").exists()

    config_path = tmp_path / ".cclaw" / "config.yaml"
    assert config_path.exists()


def test_create_bot_restarts_daemon_when_running(tmp_path, monkeypatch):
    """create_bot restarts daemon automatically when daemon is running."""
    monkeypatch.setenv("CCLAW_HOME", str(tmp_path / ".cclaw"))

    token = "123456:ABCDEF"
    bot_info = {"username": "@new_bot", "botname": "New Bot"}
    profile = {
        "name": "new-bot",
        "personality": "Helpful",
        "role": "Test",
        "goal": "",
    }

    with patch("cclaw.onboarding._is_daemon_running", return_value=True):
        with patch("cclaw.onboarding._restart_daemon") as mock_restart:
            create_bot(token, bot_info, profile)
            mock_restart.assert_called_once()


def test_create_bot_no_restart_when_daemon_not_running(tmp_path, monkeypatch):
    """create_bot does not restart when daemon is not running."""
    monkeypatch.setenv("CCLAW_HOME", str(tmp_path / ".cclaw"))

    token = "123456:ABCDEF"
    bot_info = {"username": "@new_bot", "botname": "New Bot"}
    profile = {
        "name": "new-bot",
        "personality": "Helpful",
        "role": "Test",
        "goal": "",
    }

    with patch("cclaw.onboarding._is_daemon_running", return_value=False):
        with patch("cclaw.onboarding._restart_daemon") as mock_restart:
            create_bot(token, bot_info, profile)
            mock_restart.assert_not_called()


def test_is_daemon_running_with_plist(tmp_path):
    """_is_daemon_running returns True when plist exists."""
    plist_path = tmp_path / "com.cclaw.daemon.plist"
    plist_path.write_text("<plist/>")

    with patch("cclaw.bot_manager._plist_path", return_value=plist_path):
        assert _is_daemon_running() is True


def test_is_daemon_running_without_plist(tmp_path):
    """_is_daemon_running returns False when plist does not exist."""
    plist_path = tmp_path / "com.cclaw.daemon.plist"

    with patch("cclaw.bot_manager._plist_path", return_value=plist_path):
        assert _is_daemon_running() is False


# --- Timezone onboarding tests ---


def test_save_init_config(tmp_path, monkeypatch):
    """save_init_config saves timezone and language to config.yaml."""
    monkeypatch.setenv("CCLAW_HOME", str(tmp_path / ".cclaw"))

    save_init_config("Asia/Seoul", "Korean")

    from cclaw.config import load_config

    config = load_config()
    assert config is not None
    assert config["timezone"] == "Asia/Seoul"
    assert config["language"] == "Korean"


def test_save_init_config_preserves_existing(tmp_path, monkeypatch):
    """save_init_config preserves existing config entries."""
    monkeypatch.setenv("CCLAW_HOME", str(tmp_path / ".cclaw"))

    from cclaw.config import default_config, save_config

    config = default_config()
    config["bots"] = [{"name": "existing-bot", "path": "/some/path"}]
    save_config(config)

    save_init_config("America/New_York", "English")

    from cclaw.config import load_config

    updated = load_config()
    assert updated["timezone"] == "America/New_York"
    assert updated["language"] == "English"
    assert len(updated["bots"]) == 1
    assert updated["bots"][0]["name"] == "existing-bot"


def test_prompt_timezone_accepts_default(monkeypatch):
    """prompt_timezone uses detected timezone when user provides empty input."""
    monkeypatch.setattr("cclaw.onboarding.detect_local_timezone", lambda: "Asia/Seoul")
    monkeypatch.setattr("cclaw.utils.prompt_input", lambda *a, **kw: "")

    result = prompt_timezone()
    assert result == "Asia/Seoul"


def test_prompt_timezone_accepts_custom(monkeypatch):
    """prompt_timezone uses user-provided timezone."""
    monkeypatch.setattr("cclaw.onboarding.detect_local_timezone", lambda: "Asia/Seoul")
    monkeypatch.setattr("cclaw.utils.prompt_input", lambda *a, **kw: "America/New_York")

    result = prompt_timezone()
    assert result == "America/New_York"


def test_prompt_timezone_invalid_falls_back(monkeypatch):
    """prompt_timezone falls back to detected timezone on invalid input."""
    monkeypatch.setattr("cclaw.onboarding.detect_local_timezone", lambda: "Asia/Seoul")
    monkeypatch.setattr("cclaw.utils.prompt_input", lambda *a, **kw: "Invalid/Timezone")

    result = prompt_timezone()
    assert result == "Asia/Seoul"


# --- Language onboarding tests ---


def test_prompt_language_default(monkeypatch):
    """prompt_language uses Korean when user provides empty input."""
    monkeypatch.setattr("cclaw.utils.prompt_input", lambda *a, **kw: "")

    result = prompt_language()
    assert result == "Korean"


def test_prompt_language_select_number(monkeypatch):
    """prompt_language selects language by number."""
    monkeypatch.setattr("cclaw.utils.prompt_input", lambda *a, **kw: "2")

    result = prompt_language()
    assert result == "English"


def test_prompt_language_invalid_number(monkeypatch):
    """prompt_language falls back to Korean on invalid number."""
    monkeypatch.setattr("cclaw.utils.prompt_input", lambda *a, **kw: "99")

    result = prompt_language()
    assert result == "Korean"


def test_prompt_language_invalid_text(monkeypatch):
    """prompt_language falls back to Korean on non-numeric input."""
    monkeypatch.setattr("cclaw.utils.prompt_input", lambda *a, **kw: "abc")

    result = prompt_language()
    assert result == "Korean"
