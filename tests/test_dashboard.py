"""Tests for dashboard status detection (cli.py and bot_manager.py)."""

from __future__ import annotations

import os
import socket
from unittest.mock import patch

import pytest
import yaml
from typer.testing import CliRunner

from cclaw.cli import (
    DASHBOARD_DEFAULT_PORT,
    _get_dashboard_port,
    _is_dashboard_running,
    _is_port_in_use,
    app,
)

runner = CliRunner()


@pytest.fixture()
def temp_cclaw_home(tmp_path, monkeypatch):
    """Set CCLAW_HOME to a temporary directory."""
    home = tmp_path / ".cclaw"
    home.mkdir()
    monkeypatch.setenv("CCLAW_HOME", str(home))

    config = {
        "bots": [{"name": "testbot", "path": str(home / "bots" / "testbot")}],
        "timezone": "Asia/Seoul",
        "language": "Korean",
    }
    (home / "config.yaml").write_text(
        yaml.dump(config, default_flow_style=False, allow_unicode=True)
    )

    bot_directory = home / "bots" / "testbot"
    bot_directory.mkdir(parents=True)
    bot_config = {
        "name": "testbot",
        "telegram_token": "fake-token",
        "telegram_username": "@test_bot",
        "display_name": "Test Bot",
        "personality": "Test",
        "role": "Test",
        "goal": "Test",
    }
    (bot_directory / "bot.yaml").write_text(
        yaml.dump(bot_config, default_flow_style=False, allow_unicode=True)
    )
    return home


# --- _is_port_in_use ---


def test_is_port_in_use_with_listening_socket():
    """Port with a listening socket should return True."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("localhost", 0))
        server.listen(1)
        port = server.getsockname()[1]
        assert _is_port_in_use(port) is True


def test_is_port_in_use_with_free_port():
    """Free port should return False."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("localhost", 0))
        port = server.getsockname()[1]
    # Port is now released
    assert _is_port_in_use(port) is False


# --- _is_dashboard_running ---


def test_is_dashboard_running_with_valid_pid_file(temp_cclaw_home):
    """Should detect running dashboard from pid file."""
    pid_file = temp_cclaw_home / "clawhouse.pid"
    pid_file.write_text(f"{os.getpid()}\n3847\n")

    running, pid = _is_dashboard_running()
    assert running is True
    assert pid == os.getpid()


def test_is_dashboard_running_with_stale_pid_file(temp_cclaw_home):
    """Stale pid file with dead process should be cleaned up."""
    pid_file = temp_cclaw_home / "clawhouse.pid"
    pid_file.write_text("999999\n3847\n")

    with patch("cclaw.cli._is_port_in_use", return_value=False):
        running, pid = _is_dashboard_running()

    assert running is False
    assert pid is None
    assert not pid_file.exists()


def test_is_dashboard_running_no_pid_file_port_in_use(temp_cclaw_home):
    """Should detect dashboard via port fallback when no pid file exists."""
    with patch("cclaw.cli._is_port_in_use", return_value=True):
        running, pid = _is_dashboard_running()

    assert running is True
    assert pid is None


def test_is_dashboard_running_no_pid_file_port_free(temp_cclaw_home):
    """Should report not running when no pid file and port is free."""
    with patch("cclaw.cli._is_port_in_use", return_value=False):
        running, pid = _is_dashboard_running()

    assert running is False
    assert pid is None


def test_is_dashboard_running_stale_pid_but_port_in_use(temp_cclaw_home):
    """Stale pid file but port in use should detect via port fallback."""
    pid_file = temp_cclaw_home / "clawhouse.pid"
    pid_file.write_text("999999\n3847\n")

    with patch("cclaw.cli._is_port_in_use", return_value=True):
        running, pid = _is_dashboard_running()

    assert running is True
    assert pid is None


# --- _get_dashboard_port ---


def test_get_dashboard_port_with_port_in_file(temp_cclaw_home):
    """Should read port from second line of pid file."""
    pid_file = temp_cclaw_home / "clawhouse.pid"
    pid_file.write_text(f"{os.getpid()}\n4000\n")

    assert _get_dashboard_port() == 4000


def test_get_dashboard_port_single_line(temp_cclaw_home):
    """Should return default port when pid file has only one line."""
    pid_file = temp_cclaw_home / "clawhouse.pid"
    pid_file.write_text(f"{os.getpid()}\n")

    assert _get_dashboard_port() == DASHBOARD_DEFAULT_PORT


def test_get_dashboard_port_no_file(temp_cclaw_home):
    """Should return None when no pid file exists."""
    assert _get_dashboard_port() is None


# --- dashboard status CLI command ---


def test_dashboard_status_running_with_pid(temp_cclaw_home):
    """CLI should show PID, port, and URL when pid file exists."""
    pid_file = temp_cclaw_home / "clawhouse.pid"
    pid_file.write_text(f"{os.getpid()}\n3847\n")

    result = runner.invoke(app, ["dashboard", "status"])
    assert result.exit_code == 0
    assert "running" in result.output.lower()
    assert str(os.getpid()) in result.output
    assert "3847" in result.output
    assert "http://localhost:3847" in result.output


def test_dashboard_status_running_without_pid(temp_cclaw_home):
    """CLI should show port and URL even without PID (port fallback)."""
    with patch("cclaw.cli._is_dashboard_running", return_value=(True, None)):
        with patch("cclaw.cli._get_dashboard_port", return_value=None):
            result = runner.invoke(app, ["dashboard", "status"])

    assert result.exit_code == 0
    assert "running" in result.output.lower()
    assert "PID" not in result.output
    assert "http://localhost:3847" in result.output


def test_dashboard_status_not_running(temp_cclaw_home):
    """CLI should show not running message."""
    with patch("cclaw.cli._is_dashboard_running", return_value=(False, None)):
        result = runner.invoke(app, ["dashboard", "status"])

    assert result.exit_code == 0
    assert "not running" in result.output.lower()


# --- bot_manager _show_dashboard_status ---


def test_show_dashboard_status_with_pid_file(temp_cclaw_home, capsys):
    """Should show dashboard info with PID when pid file exists."""
    from cclaw.bot_manager import _show_dashboard_status

    pid_file = temp_cclaw_home / "clawhouse.pid"
    pid_file.write_text(f"{os.getpid()}\n3847\n")

    _show_dashboard_status()
    captured = capsys.readouterr()
    assert "running" in captured.out.lower() or "Dashboard" in captured.out


def test_show_dashboard_status_port_fallback(temp_cclaw_home, capsys):
    """Should detect dashboard via port when no pid file."""
    from cclaw.bot_manager import _show_dashboard_status

    with patch("cclaw.bot_manager._is_port_in_use", return_value=True):
        with patch("cclaw.bot_manager._get_local_ip", return_value="192.168.1.100"):
            _show_dashboard_status()

    captured = capsys.readouterr()
    assert "running" in captured.out.lower() or "Dashboard" in captured.out


def test_show_dashboard_status_not_running(temp_cclaw_home, capsys):
    """Should show not running when no pid file and port is free."""
    from cclaw.bot_manager import _show_dashboard_status

    with patch("cclaw.bot_manager._is_port_in_use", return_value=False):
        _show_dashboard_status()

    captured = capsys.readouterr()
    assert "not running" in captured.out.lower()


# --- bot_manager _get_local_ip ---


def test_get_local_ip_returns_valid_ip():
    """Should return a valid IP address string."""
    from cclaw.bot_manager import _get_local_ip

    ip_address = _get_local_ip()
    parts = ip_address.split(".")
    assert len(parts) == 4
    assert all(part.isdigit() for part in parts)


def test_get_local_ip_fallback_on_error():
    """Should return 127.0.0.1 when socket fails."""
    from cclaw.bot_manager import _get_local_ip

    with patch("socket.socket") as mock_socket:
        mock_socket.return_value.__enter__ = lambda s: s
        mock_socket.return_value.__exit__ = lambda s, *a: None
        mock_socket.return_value.connect.side_effect = OSError("no network")
        ip_address = _get_local_ip()

    assert ip_address == "127.0.0.1"
