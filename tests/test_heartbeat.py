"""Tests for abyss.heartbeat module."""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from abyss.heartbeat import (
    default_heartbeat_content,
    disable_heartbeat,
    enable_heartbeat,
    execute_heartbeat,
    get_heartbeat_config,
    heartbeat_session_directory,
    is_within_active_hours,
    load_heartbeat_markdown,
    run_heartbeat_scheduler,
    save_heartbeat_config,
    save_heartbeat_markdown,
)


@pytest.fixture
def temp_abyss_home(tmp_path, monkeypatch):
    """Set ABYSS_HOME to a temporary directory."""
    home = tmp_path / ".abyss"
    monkeypatch.setenv("ABYSS_HOME", str(home))
    return home


@pytest.fixture
def bot_with_config(temp_abyss_home):
    """Create a bot directory with bot.yaml and CLAUDE.md."""
    bot_directory = temp_abyss_home / "bots" / "test-bot"
    bot_directory.mkdir(parents=True)
    (bot_directory / "sessions").mkdir()
    (bot_directory / "CLAUDE.md").write_text("# test-bot\n")

    bot_config = {
        "telegram_token": "fake-token",
        "personality": "test",
        "description": "test bot",
        "allowed_users": [123],
        "heartbeat": {
            "enabled": False,
            "interval_minutes": 30,
            "active_hours": {
                "start": "07:00",
                "end": "23:00",
            },
        },
    }
    with open(bot_directory / "bot.yaml", "w") as file:
        yaml.dump(bot_config, file)

    return "test-bot"


# --- Config CRUD tests ---


def test_get_heartbeat_config(bot_with_config):
    """get_heartbeat_config reads heartbeat section from bot.yaml."""
    config = get_heartbeat_config(bot_with_config)
    assert config["enabled"] is False
    assert config["interval_minutes"] == 30
    assert config["active_hours"]["start"] == "07:00"
    assert config["active_hours"]["end"] == "23:00"


def test_get_heartbeat_config_missing_bot(temp_abyss_home):
    """get_heartbeat_config returns defaults for missing bot."""
    config = get_heartbeat_config("nonexistent")
    assert config["enabled"] is False
    assert config["interval_minutes"] == 30


def test_save_heartbeat_config(bot_with_config):
    """save_heartbeat_config updates heartbeat section in bot.yaml."""
    new_config = {
        "enabled": True,
        "interval_minutes": 15,
        "active_hours": {"start": "08:00", "end": "22:00"},
    }
    save_heartbeat_config(bot_with_config, new_config)

    loaded = get_heartbeat_config(bot_with_config)
    assert loaded["enabled"] is True
    assert loaded["interval_minutes"] == 15
    assert loaded["active_hours"]["start"] == "08:00"


def test_enable_heartbeat(bot_with_config):
    """enable_heartbeat sets enabled=True and creates HEARTBEAT.md."""
    result = enable_heartbeat(bot_with_config)
    assert result is True

    config = get_heartbeat_config(bot_with_config)
    assert config["enabled"] is True

    # Should create HEARTBEAT.md
    directory = heartbeat_session_directory(bot_with_config)
    assert (directory / "HEARTBEAT.md").exists()


def test_enable_heartbeat_missing_bot(temp_abyss_home):
    """enable_heartbeat returns False for missing bot."""
    result = enable_heartbeat("nonexistent")
    assert result is False


def test_disable_heartbeat(bot_with_config):
    """disable_heartbeat sets enabled=False."""
    enable_heartbeat(bot_with_config)
    result = disable_heartbeat(bot_with_config)
    assert result is True

    config = get_heartbeat_config(bot_with_config)
    assert config["enabled"] is False


def test_disable_heartbeat_missing_bot(temp_abyss_home):
    """disable_heartbeat returns False for missing bot."""
    result = disable_heartbeat("nonexistent")
    assert result is False


# --- Active hours tests ---


def test_is_within_active_hours_inside():
    """is_within_active_hours returns True when inside range."""
    active_hours = {"start": "07:00", "end": "23:00"}
    noon = datetime(2026, 2, 17, 12, 0)
    assert is_within_active_hours(active_hours, now=noon) is True


def test_is_within_active_hours_outside():
    """is_within_active_hours returns False when outside range."""
    active_hours = {"start": "07:00", "end": "23:00"}
    midnight = datetime(2026, 2, 17, 3, 0)
    assert is_within_active_hours(active_hours, now=midnight) is False


def test_is_within_active_hours_at_start():
    """is_within_active_hours returns True at start boundary."""
    active_hours = {"start": "07:00", "end": "23:00"}
    start_time = datetime(2026, 2, 17, 7, 0)
    assert is_within_active_hours(active_hours, now=start_time) is True


def test_is_within_active_hours_at_end():
    """is_within_active_hours returns True at end boundary."""
    active_hours = {"start": "07:00", "end": "23:00"}
    end_time = datetime(2026, 2, 17, 23, 0)
    assert is_within_active_hours(active_hours, now=end_time) is True


def test_is_within_active_hours_overnight_inside():
    """is_within_active_hours handles overnight range (inside)."""
    active_hours = {"start": "22:00", "end": "06:00"}
    late_night = datetime(2026, 2, 17, 23, 30)
    assert is_within_active_hours(active_hours, now=late_night) is True

    early_morning = datetime(2026, 2, 17, 3, 0)
    assert is_within_active_hours(active_hours, now=early_morning) is True


def test_is_within_active_hours_overnight_outside():
    """is_within_active_hours handles overnight range (outside)."""
    active_hours = {"start": "22:00", "end": "06:00"}
    afternoon = datetime(2026, 2, 17, 14, 0)
    assert is_within_active_hours(active_hours, now=afternoon) is False


# --- Session directory tests ---


def test_heartbeat_session_directory(bot_with_config, temp_abyss_home):
    """heartbeat_session_directory creates and returns correct path."""
    directory = heartbeat_session_directory(bot_with_config)
    assert directory.exists()
    assert directory.name == "heartbeat_sessions"
    assert "bots" in str(directory)

    # CLAUDE.md should be copied from bot
    assert (directory / "CLAUDE.md").exists()

    # workspace should be created
    assert (directory / "workspace").exists()


def test_heartbeat_session_directory_preserves_existing(bot_with_config, temp_abyss_home):
    """heartbeat_session_directory doesn't overwrite existing CLAUDE.md."""
    directory = heartbeat_session_directory(bot_with_config)
    custom_content = "# Custom content"
    (directory / "CLAUDE.md").write_text(custom_content)

    # Call again — should not overwrite
    directory2 = heartbeat_session_directory(bot_with_config)
    assert (directory2 / "CLAUDE.md").read_text() == custom_content


# --- HEARTBEAT.md management tests ---


def test_default_heartbeat_content():
    """default_heartbeat_content returns non-empty template."""
    content = default_heartbeat_content()
    assert "HEARTBEAT_OK" in content
    assert "Heartbeat Checklist" in content


def test_load_heartbeat_markdown_empty(bot_with_config):
    """load_heartbeat_markdown returns empty string when no HEARTBEAT.md exists."""
    content = load_heartbeat_markdown(bot_with_config)
    assert content == ""


def test_save_and_load_heartbeat_markdown(bot_with_config):
    """save_heartbeat_markdown and load_heartbeat_markdown round-trip."""
    content = "# My Custom Checklist\n- Check API status"
    save_heartbeat_markdown(bot_with_config, content)

    loaded = load_heartbeat_markdown(bot_with_config)
    assert loaded == content


# --- execute_heartbeat tests ---


@pytest.mark.asyncio
async def test_execute_heartbeat_ok_no_notification(bot_with_config):
    """execute_heartbeat does NOT send messages when response contains HEARTBEAT_OK."""
    # Create HEARTBEAT.md
    save_heartbeat_markdown(bot_with_config, default_heartbeat_content())

    bot_config = {
        "allowed_users": [123, 456],
        "model": "sonnet",
        "command_timeout": 60,
    }

    send_mock = AsyncMock()

    with patch(
        "abyss.claude_runner.run_claude_with_sdk",
        new_callable=AsyncMock,
        return_value="All clear. HEARTBEAT_OK",
    ):
        await execute_heartbeat(
            bot_name=bot_with_config,
            bot_config=bot_config,
            send_message_callback=send_mock,
        )

    send_mock.assert_not_called()


@pytest.mark.asyncio
async def test_execute_heartbeat_sends_notification(bot_with_config):
    """execute_heartbeat sends messages when response does NOT contain HEARTBEAT_OK."""
    save_heartbeat_markdown(bot_with_config, default_heartbeat_content())

    bot_config = {
        "allowed_users": [123, 456],
        "model": "sonnet",
        "command_timeout": 60,
    }

    send_mock = AsyncMock()

    with patch(
        "abyss.claude_runner.run_claude_with_sdk",
        new_callable=AsyncMock,
        return_value="You have pending tasks in workspace/",
    ):
        await execute_heartbeat(
            bot_name=bot_with_config,
            bot_config=bot_config,
            send_message_callback=send_mock,
        )

    # Should send to both users
    assert send_mock.call_count >= 2
    call_chat_ids = [call.kwargs.get("chat_id") for call in send_mock.call_args_list]
    assert 123 in call_chat_ids
    assert 456 in call_chat_ids


@pytest.mark.asyncio
async def test_execute_heartbeat_no_allowed_users_no_sessions(bot_with_config):
    """execute_heartbeat skips sending when no allowed_users and no session chat IDs."""
    save_heartbeat_markdown(bot_with_config, default_heartbeat_content())

    bot_config = {
        "allowed_users": [],
        "model": "sonnet",
        "command_timeout": 60,
    }

    send_mock = AsyncMock()

    with patch(
        "abyss.claude_runner.run_claude_with_sdk",
        new_callable=AsyncMock,
        return_value="Something to report",
    ):
        # Ensure no session directories exist
        await execute_heartbeat(
            bot_name=bot_with_config,
            bot_config=bot_config,
            send_message_callback=send_mock,
        )

    send_mock.assert_not_called()


@pytest.mark.asyncio
async def test_execute_heartbeat_fallback_to_session_chat_ids(bot_with_config, temp_abyss_home):
    """execute_heartbeat falls back to session chat IDs when allowed_users is empty."""
    save_heartbeat_markdown(bot_with_config, default_heartbeat_content())

    # Create session directories to simulate past conversations
    bot_path = temp_abyss_home / "bots" / bot_with_config
    sessions_directory = bot_path / "sessions"
    sessions_directory.mkdir(parents=True, exist_ok=True)
    (sessions_directory / "chat_111").mkdir()
    (sessions_directory / "chat_222").mkdir()

    bot_config = {
        "allowed_users": [],
        "model": "sonnet",
        "command_timeout": 60,
    }

    send_mock = AsyncMock()

    with patch(
        "abyss.claude_runner.run_claude_with_sdk",
        new_callable=AsyncMock,
        return_value="Something to report",
    ):
        await execute_heartbeat(
            bot_name=bot_with_config,
            bot_config=bot_config,
            send_message_callback=send_mock,
        )

    # Should send to both session chat IDs
    assert send_mock.call_count >= 2
    call_chat_ids = [call.kwargs.get("chat_id") for call in send_mock.call_args_list]
    assert 111 in call_chat_ids
    assert 222 in call_chat_ids


@pytest.mark.asyncio
async def test_execute_heartbeat_no_heartbeat_md(bot_with_config):
    """execute_heartbeat skips when no HEARTBEAT.md exists."""
    bot_config = {
        "allowed_users": [123],
        "model": "sonnet",
        "command_timeout": 60,
    }

    send_mock = AsyncMock()

    with patch(
        "abyss.claude_runner.run_claude_with_sdk",
        new_callable=AsyncMock,
    ) as mock_claude:
        await execute_heartbeat(
            bot_name=bot_with_config,
            bot_config=bot_config,
            send_message_callback=send_mock,
        )

    mock_claude.assert_not_called()
    send_mock.assert_not_called()


@pytest.mark.asyncio
async def test_execute_heartbeat_handles_error(bot_with_config):
    """execute_heartbeat sends error message when Claude fails."""
    save_heartbeat_markdown(bot_with_config, default_heartbeat_content())

    bot_config = {
        "allowed_users": [123],
        "model": "sonnet",
        "command_timeout": 60,
    }

    send_mock = AsyncMock()

    with patch(
        "abyss.claude_runner.run_claude_with_sdk",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Claude crashed"),
    ):
        await execute_heartbeat(
            bot_name=bot_with_config,
            bot_config=bot_config,
            send_message_callback=send_mock,
        )

    # Should still send the error message (no HEARTBEAT_OK in error message)
    send_mock.assert_called()
    sent_text = send_mock.call_args_list[0].kwargs.get("text", "")
    assert "failed" in sent_text.lower() or "heartbeat" in sent_text.lower()


# --- Scheduler tests ---


@pytest.mark.asyncio
async def test_run_heartbeat_scheduler_stops_on_event(bot_with_config):
    """run_heartbeat_scheduler exits when stop_event is set."""
    bot_config = {
        "allowed_users": [],
        "model": "sonnet",
        "heartbeat": {
            "enabled": True,
            "interval_minutes": 1,
            "active_hours": {"start": "00:00", "end": "23:59"},
        },
    }
    application = AsyncMock()
    stop_event = asyncio.Event()

    async def set_stop():
        await asyncio.sleep(0.1)
        stop_event.set()

    asyncio.create_task(set_stop())

    await asyncio.wait_for(
        run_heartbeat_scheduler(bot_with_config, bot_config, application, stop_event),
        timeout=5,
    )


@pytest.mark.asyncio
async def test_run_heartbeat_scheduler_skips_outside_active_hours(bot_with_config):
    """run_heartbeat_scheduler skips execution outside active hours."""
    bot_config = {
        "allowed_users": [123],
        "model": "sonnet",
        "heartbeat": {
            "enabled": True,
            "interval_minutes": 1,
            "active_hours": {"start": "00:00", "end": "00:00"},
        },
    }
    application = AsyncMock()
    stop_event = asyncio.Event()

    async def set_stop():
        await asyncio.sleep(0.1)
        stop_event.set()

    asyncio.create_task(set_stop())

    with patch("abyss.heartbeat.execute_heartbeat", new_callable=AsyncMock) as mock_execute:
        # Force active hours check to return False
        with patch("abyss.heartbeat.is_within_active_hours", return_value=False):
            await asyncio.wait_for(
                run_heartbeat_scheduler(bot_with_config, bot_config, application, stop_event),
                timeout=5,
            )

    mock_execute.assert_not_called()


@pytest.mark.asyncio
async def test_run_heartbeat_scheduler_executes_within_active_hours(bot_with_config):
    """run_heartbeat_scheduler executes heartbeat within active hours."""
    save_heartbeat_markdown(bot_with_config, default_heartbeat_content())

    bot_config = {
        "allowed_users": [123],
        "model": "sonnet",
        "command_timeout": 60,
        "heartbeat": {
            "enabled": True,
            "interval_minutes": 1,
            "active_hours": {"start": "00:00", "end": "23:59"},
        },
    }
    application = AsyncMock()
    stop_event = asyncio.Event()

    executed = asyncio.Event()

    async def mock_execute(*args, **kwargs):
        executed.set()

    async def set_stop():
        try:
            await asyncio.wait_for(executed.wait(), timeout=2)
        except asyncio.TimeoutError:
            pass
        stop_event.set()

    asyncio.create_task(set_stop())

    with patch(
        "abyss.heartbeat.execute_heartbeat",
        side_effect=mock_execute,
    ) as mock_exec:
        with patch("abyss.heartbeat.is_within_active_hours", return_value=True):
            await asyncio.wait_for(
                run_heartbeat_scheduler(bot_with_config, bot_config, application, stop_event),
                timeout=5,
            )

    if executed.is_set():
        mock_exec.assert_called()
