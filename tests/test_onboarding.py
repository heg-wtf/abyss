"""Tests for abyss.onboarding module."""

from unittest.mock import MagicMock, patch

from abyss.onboarding import (
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
)


def test_check_python():
    """check_python should always succeed."""
    result = check_python()
    assert result.available is True
    assert result.name == "Python"
    assert result.version


def test_check_node_installed():
    """check_node returns available=True when node is found."""
    with patch("abyss.onboarding.shutil.which", return_value="/usr/local/bin/node"):
        with patch("abyss.onboarding.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="v20.11.0\n", stderr="")
            result = check_node()
            assert result.available is True
            assert "20" in result.version


def test_check_node_missing():
    """check_node returns available=False when node is not found."""
    with patch("abyss.onboarding.shutil.which", return_value=None):
        result = check_node()
        assert result.available is False


def test_check_claude_code_installed():
    """check_claude_code returns available=True when claude is found."""
    with patch("abyss.onboarding.shutil.which", return_value="/usr/local/bin/claude"):
        with patch("abyss.onboarding.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="1.0.23\n", stderr="")
            result = check_claude_code()
            assert result.available is True
            assert "1.0.23" in result.version


def test_check_claude_code_missing():
    """check_claude_code returns available=False when claude is not found."""
    with patch("abyss.onboarding.shutil.which", return_value=None):
        result = check_claude_code()
        assert result.available is False
        assert "npm install" in result.message


def test_run_environment_checks():
    """run_environment_checks returns Python, Node, Claude Code, and SQLite FTS5 checks."""
    with patch("abyss.onboarding.shutil.which", return_value="/usr/bin/fake"):
        with patch("abyss.onboarding.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="v1.0.0\n", stderr="")
            checks = run_environment_checks()
            assert len(checks) == 4
            assert all(isinstance(c, EnvironmentCheckResult) for c in checks)
            names = {c.name for c in checks}
            assert "SQLite FTS5" in names


def test_create_bot(tmp_path, monkeypatch):
    """create_bot creates all necessary files (no Telegram token)."""
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path / ".abyss"))

    profile = {
        "name": "test-bot",
        "display_name": "My Test Bot",
        "personality": "Helpful assistant",
        "role": "General help",
        "goal": "Make life easier",
    }

    create_bot(profile)

    bot_directory = tmp_path / ".abyss" / "bots" / "test-bot"
    assert (bot_directory / "bot.yaml").exists()
    assert (bot_directory / "CLAUDE.md").exists()
    assert (bot_directory / "sessions").exists()

    config_path = tmp_path / ".abyss" / "config.yaml"
    assert config_path.exists()


def test_create_bot_with_explicit_backend_block(tmp_path, monkeypatch):
    """create_bot writes the backend block when one is supplied.

    Kept after the v2026.05.15 OpenAI-compat removal because future
    full-agent backends will reuse the same code path.
    """
    import yaml

    monkeypatch.setenv("ABYSS_HOME", str(tmp_path / ".abyss"))

    backend_block = {"type": "claude_code", "model": "opus"}
    create_bot(
        profile={
            "name": "explicit-bot",
            "display_name": "Explicit Bot",
            "personality": "Helpful",
            "role": "Test",
            "goal": "",
        },
        backend_block=backend_block,
    )

    bot_yaml = tmp_path / ".abyss" / "bots" / "explicit-bot" / "bot.yaml"
    saved = yaml.safe_load(bot_yaml.read_text())
    assert saved["backend"] == backend_block


def test_prompt_backend_choice_returns_none_post_compat_removal(monkeypatch):
    """``prompt_backend_choice`` is a no-op since v2026.05.15 — always returns None."""
    from abyss import onboarding

    assert onboarding.prompt_backend_choice() is None


def test_create_bot_restarts_daemon_when_running(tmp_path, monkeypatch):
    """create_bot restarts daemon automatically when daemon is running."""
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path / ".abyss"))

    profile = {
        "name": "new-bot",
        "personality": "Helpful",
        "role": "Test",
        "goal": "",
    }

    with patch("abyss.onboarding._is_daemon_running", return_value=True):
        with patch("abyss.onboarding._restart_daemon") as mock_restart:
            create_bot(profile)
            mock_restart.assert_called_once()


def test_create_bot_no_restart_when_daemon_not_running(tmp_path, monkeypatch):
    """create_bot does not restart when daemon is not running."""
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path / ".abyss"))

    profile = {
        "name": "new-bot",
        "personality": "Helpful",
        "role": "Test",
        "goal": "",
    }

    with patch("abyss.onboarding._is_daemon_running", return_value=False):
        with patch("abyss.onboarding._restart_daemon") as mock_restart:
            create_bot(profile)
            mock_restart.assert_not_called()


def test_is_daemon_running_with_plist(tmp_path):
    """_is_daemon_running returns True when plist exists."""
    plist_path = tmp_path / "com.abyss.daemon.plist"
    plist_path.write_text("<plist/>")

    with patch("abyss.bot_manager._plist_path", return_value=plist_path):
        assert _is_daemon_running() is True


def test_is_daemon_running_without_plist(tmp_path):
    """_is_daemon_running returns False when plist does not exist."""
    plist_path = tmp_path / "com.abyss.daemon.plist"

    with patch("abyss.bot_manager._plist_path", return_value=plist_path):
        assert _is_daemon_running() is False


# --- Timezone onboarding tests ---


def test_save_init_config(tmp_path, monkeypatch):
    """save_init_config saves timezone and language to config.yaml."""
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path / ".abyss"))

    save_init_config("Asia/Seoul", "Korean")

    from abyss.config import load_config

    config = load_config()
    assert config is not None
    assert config["timezone"] == "Asia/Seoul"
    assert config["language"] == "Korean"


def test_save_init_config_preserves_existing(tmp_path, monkeypatch):
    """save_init_config preserves existing config entries."""
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path / ".abyss"))

    from abyss.config import default_config, save_config

    config = default_config()
    config["bots"] = [{"name": "existing-bot", "path": "/some/path"}]
    save_config(config)

    save_init_config("America/New_York", "English")

    from abyss.config import load_config

    updated = load_config()
    assert updated["timezone"] == "America/New_York"
    assert updated["language"] == "English"
    assert len(updated["bots"]) == 1
    assert updated["bots"][0]["name"] == "existing-bot"


def test_prompt_timezone_accepts_default(monkeypatch):
    """prompt_timezone uses detected timezone when user provides empty input."""
    monkeypatch.setattr("abyss.onboarding.detect_local_timezone", lambda: "Asia/Seoul")
    monkeypatch.setattr("abyss.utils.prompt_input", lambda *a, **kw: "")

    result = prompt_timezone()
    assert result == "Asia/Seoul"


def test_prompt_timezone_accepts_custom(monkeypatch):
    """prompt_timezone uses user-provided timezone."""
    monkeypatch.setattr("abyss.onboarding.detect_local_timezone", lambda: "Asia/Seoul")
    monkeypatch.setattr("abyss.utils.prompt_input", lambda *a, **kw: "America/New_York")

    result = prompt_timezone()
    assert result == "America/New_York"


def test_prompt_timezone_invalid_falls_back(monkeypatch):
    """prompt_timezone falls back to detected timezone on invalid input."""
    monkeypatch.setattr("abyss.onboarding.detect_local_timezone", lambda: "Asia/Seoul")
    monkeypatch.setattr("abyss.utils.prompt_input", lambda *a, **kw: "Invalid/Timezone")

    result = prompt_timezone()
    assert result == "Asia/Seoul"


# --- Language onboarding tests ---


def test_prompt_language_default(monkeypatch):
    """prompt_language uses Korean when user provides empty input."""
    monkeypatch.setattr("abyss.utils.prompt_input", lambda *a, **kw: "")

    result = prompt_language()
    assert result == "Korean"


def test_prompt_language_select_number(monkeypatch):
    """prompt_language selects language by number."""
    monkeypatch.setattr("abyss.utils.prompt_input", lambda *a, **kw: "2")

    result = prompt_language()
    assert result == "English"


def test_prompt_language_invalid_number(monkeypatch):
    """prompt_language falls back to Korean on invalid number."""
    monkeypatch.setattr("abyss.utils.prompt_input", lambda *a, **kw: "99")

    result = prompt_language()
    assert result == "Korean"


def test_prompt_language_invalid_text(monkeypatch):
    """prompt_language falls back to Korean on non-numeric input."""
    monkeypatch.setattr("abyss.utils.prompt_input", lambda *a, **kw: "abc")

    result = prompt_language()
    assert result == "Korean"
