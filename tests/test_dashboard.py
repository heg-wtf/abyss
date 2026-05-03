"""Tests for dashboard status detection (cli.py and bot_manager.py)."""

from __future__ import annotations

import os
import socket
from unittest.mock import patch

import pytest
import yaml
from typer.testing import CliRunner

from abyss.cli import (
    DASHBOARD_DEFAULT_PORT,
    _get_dashboard_port,
    _is_dashboard_running,
    _is_port_in_use,
    app,
)

runner = CliRunner()


@pytest.fixture()
def temp_abyss_home(tmp_path, monkeypatch):
    """Set ABYSS_HOME to a temporary directory."""
    home = tmp_path / ".abyss"
    home.mkdir()
    monkeypatch.setenv("ABYSS_HOME", str(home))

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


def test_is_dashboard_running_with_valid_pid_file(temp_abyss_home):
    """Should detect running dashboard from pid file."""
    pid_file = temp_abyss_home / "abysscope.pid"
    pid_file.write_text(f"{os.getpid()}\n3847\n")

    running, pid = _is_dashboard_running()
    assert running is True
    assert pid == os.getpid()


def test_is_dashboard_running_with_stale_pid_file(temp_abyss_home):
    """Stale pid file with dead process should be cleaned up."""
    pid_file = temp_abyss_home / "abysscope.pid"
    pid_file.write_text("999999\n3847\n")

    with patch("abyss.cli._is_port_in_use", return_value=False):
        running, pid = _is_dashboard_running()

    assert running is False
    assert pid is None
    assert not pid_file.exists()


def test_is_dashboard_running_no_pid_file_port_in_use(temp_abyss_home):
    """Should detect dashboard via port fallback when no pid file exists."""
    with patch("abyss.cli._is_port_in_use", return_value=True):
        running, pid = _is_dashboard_running()

    assert running is True
    assert pid is None


def test_is_dashboard_running_no_pid_file_port_free(temp_abyss_home):
    """Should report not running when no pid file and port is free."""
    with patch("abyss.cli._is_port_in_use", return_value=False):
        running, pid = _is_dashboard_running()

    assert running is False
    assert pid is None


def test_is_dashboard_running_stale_pid_but_port_in_use(temp_abyss_home):
    """Stale pid file but port in use should detect via port fallback."""
    pid_file = temp_abyss_home / "abysscope.pid"
    pid_file.write_text("999999\n3847\n")

    with patch("abyss.cli._is_port_in_use", return_value=True):
        running, pid = _is_dashboard_running()

    assert running is True
    assert pid is None


# --- _get_dashboard_port ---


def test_get_dashboard_port_with_port_in_file(temp_abyss_home):
    """Should read port from second line of pid file."""
    pid_file = temp_abyss_home / "abysscope.pid"
    pid_file.write_text(f"{os.getpid()}\n4000\n")

    assert _get_dashboard_port() == 4000


def test_get_dashboard_port_single_line(temp_abyss_home):
    """Should return default port when pid file has only one line."""
    pid_file = temp_abyss_home / "abysscope.pid"
    pid_file.write_text(f"{os.getpid()}\n")

    assert _get_dashboard_port() == DASHBOARD_DEFAULT_PORT


def test_get_dashboard_port_no_file(temp_abyss_home):
    """Should return None when no pid file exists."""
    assert _get_dashboard_port() is None


# --- dashboard status CLI command ---


def test_dashboard_status_running_with_pid(temp_abyss_home):
    """CLI should show PID, port, and URL when pid file exists."""
    pid_file = temp_abyss_home / "abysscope.pid"
    pid_file.write_text(f"{os.getpid()}\n3847\n")

    result = runner.invoke(app, ["dashboard", "status"])
    assert result.exit_code == 0
    assert "running" in result.output.lower()
    assert str(os.getpid()) in result.output
    assert "3847" in result.output
    assert "http://localhost:3847" in result.output


def test_dashboard_status_running_without_pid(temp_abyss_home):
    """CLI should show port and URL even without PID (port fallback)."""
    with patch("abyss.cli._is_dashboard_running", return_value=(True, None)):
        with patch("abyss.cli._get_dashboard_port", return_value=None):
            result = runner.invoke(app, ["dashboard", "status"])

    assert result.exit_code == 0
    assert "running" in result.output.lower()
    assert "PID" not in result.output
    assert "http://localhost:3847" in result.output


def test_dashboard_status_not_running(temp_abyss_home):
    """CLI should show not running message."""
    with patch("abyss.cli._is_dashboard_running", return_value=(False, None)):
        result = runner.invoke(app, ["dashboard", "status"])

    assert result.exit_code == 0
    assert "not running" in result.output.lower()


# --- bot_manager _show_dashboard_status ---


def test_show_dashboard_status_with_pid_file(temp_abyss_home, capsys):
    """Should show dashboard info with PID when pid file exists."""
    from abyss.bot_manager import _show_dashboard_status

    pid_file = temp_abyss_home / "abysscope.pid"
    pid_file.write_text(f"{os.getpid()}\n3847\n")

    _show_dashboard_status()
    captured = capsys.readouterr()
    assert "running" in captured.out.lower() or "Dashboard" in captured.out


def test_show_dashboard_status_port_fallback(temp_abyss_home, capsys):
    """Should detect dashboard via port when no pid file."""
    from abyss.bot_manager import _show_dashboard_status

    with patch("abyss.bot_manager._is_port_in_use", return_value=True):
        with patch("abyss.bot_manager._get_local_ip", return_value="192.168.1.100"):
            _show_dashboard_status()

    captured = capsys.readouterr()
    assert "running" in captured.out.lower() or "Dashboard" in captured.out


def test_show_dashboard_status_not_running(temp_abyss_home, capsys):
    """Should show not running when no pid file and port is free."""
    from abyss.bot_manager import _show_dashboard_status

    with patch("abyss.bot_manager._is_port_in_use", return_value=False):
        _show_dashboard_status()

    captured = capsys.readouterr()
    assert "not running" in captured.out.lower()


# --- bot_manager _get_local_ip ---


def test_get_local_ip_returns_valid_ip():
    """Should return a valid IP address string."""
    from abyss.bot_manager import _get_local_ip

    ip_address = _get_local_ip()
    parts = ip_address.split(".")
    assert len(parts) == 4
    assert all(part.isdigit() for part in parts)


def test_get_local_ip_fallback_on_error():
    """Should return 127.0.0.1 when socket fails."""
    from abyss.bot_manager import _get_local_ip

    with patch("socket.socket") as mock_socket:
        mock_socket.return_value.__enter__ = lambda s: s
        mock_socket.return_value.__exit__ = lambda s, *a: None
        mock_socket.return_value.connect.side_effect = OSError("no network")
        ip_address = _get_local_ip()

    assert ip_address == "127.0.0.1"


# --- cli helper functions added with the build progress UI ---


def test_format_size_boundaries():
    from abyss.cli import _format_size

    assert _format_size(0) == "0 B"
    assert _format_size(512) == "512 B"
    assert _format_size(1024) == "1.0 KB"
    assert _format_size(1024 * 1024) == "1.0 MB"
    assert _format_size(1024 * 1024 * 1024) == "1.00 GB"
    assert _format_size(1024 * 1024 * 1024 * 5) == "5.00 GB"


def test_format_directory_relative_when_inside_cwd(tmp_path, monkeypatch):
    from abyss.cli import _format_directory

    monkeypatch.chdir(tmp_path)
    sub = tmp_path / "abysscope"
    sub.mkdir()
    assert _format_directory(sub) == "abysscope"


def test_format_directory_absolute_when_outside_cwd(tmp_path, monkeypatch):
    from abyss.cli import _format_directory

    other = tmp_path / "elsewhere"
    other.mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    assert _format_directory(other) == str(other.resolve())


def test_node_modules_present_detection(tmp_path):
    from abyss.cli import _node_modules_present

    assert _node_modules_present(tmp_path) is False
    (tmp_path / "node_modules").mkdir()
    assert _node_modules_present(tmp_path) is True


def test_run_to_log_writes_command_header_and_returns_exit_code(tmp_path):
    from abyss.cli import _run_to_log

    log = tmp_path / "build.log"
    code = _run_to_log(["true"], cwd=tmp_path, env=os.environ.copy(), log_path=log)
    assert code == 0
    contents = log.read_text()
    assert contents.startswith("\n$ true\n")


def test_run_to_log_captures_failure_exit_code(tmp_path):
    from abyss.cli import _run_to_log

    log = tmp_path / "build.log"
    code = _run_to_log(
        ["sh", "-c", "echo failing 1>&2; exit 7"],
        cwd=tmp_path,
        env=os.environ.copy(),
        log_path=log,
    )
    assert code == 7
    assert "failing" in log.read_text()


def test_next_build_artifact_size_sums_files(tmp_path):
    from abyss.cli import _next_build_artifact_size

    assert _next_build_artifact_size(tmp_path) == 0  # no .next yet

    next_dir = tmp_path / ".next"
    (next_dir / "static" / "chunks").mkdir(parents=True)
    (next_dir / "static" / "chunks" / "main.js").write_bytes(b"abc" * 1000)
    (next_dir / "BUILD_ID").write_bytes(b"1")
    assert _next_build_artifact_size(tmp_path) == 3 * 1000 + 1


def test_ensure_conversation_index_creates_bot_db(temp_abyss_home, monkeypatch):
    """Bot start hook ensures the FTS5 schema exists on every run."""
    from abyss import conversation_index
    from abyss.bot_manager import _ensure_conversation_index

    if not conversation_index.is_fts5_available():
        pytest.skip("FTS5 not available on this build")

    monkeypatch.setattr("abyss.group.find_groups_for_bot", lambda _name: [])
    bot_path = temp_abyss_home / "bots" / "alpha"
    bot_path.mkdir(parents=True)
    _ensure_conversation_index("alpha", bot_path)
    assert (bot_path / "conversation.db").is_file()


def test_ensure_conversation_index_skips_when_fts5_unavailable(
    temp_abyss_home, monkeypatch, caplog
):
    """When FTS5 is missing the helper logs once and short-circuits."""
    import logging

    from abyss.bot_manager import _ensure_conversation_index

    monkeypatch.setattr("abyss.conversation_index.is_fts5_available", lambda: False)
    bot_path = temp_abyss_home / "bots" / "alpha"
    bot_path.mkdir(parents=True)
    with caplog.at_level(logging.WARNING):
        _ensure_conversation_index("alpha", bot_path)
    assert not (bot_path / "conversation.db").exists()
    assert any("FTS5" in record.message for record in caplog.records)


def test_ensure_qmd_conversations_collection_skips_when_no_bots(tmp_path, monkeypatch):
    """No bots/ tree → no QMD subprocess invocation."""
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
    from abyss.bot_manager import _ensure_qmd_conversations_collection

    called: list[bool] = []

    def _fake_run(*_args, **_kwargs):
        called.append(True)
        raise AssertionError("subprocess should not be invoked when bots/ is missing")

    monkeypatch.setattr("subprocess.run", _fake_run)
    _ensure_qmd_conversations_collection()
    assert called == []


def test_stop_qmd_daemon_no_op_when_qmd_missing(monkeypatch):
    """`abyss start` shutdown path shouldn't fail when qmd isn't installed."""
    from abyss.bot_manager import _stop_qmd_daemon

    monkeypatch.setattr("shutil.which", lambda _name: None)
    # Just confirming the function returns without raising.
    _stop_qmd_daemon()


def test_qmd_health_check_returns_false_on_connection_error(monkeypatch):
    """Health check uses asyncio.open_connection; a refusal must report unreachable."""
    import asyncio

    from abyss.bot_manager import _qmd_health_check

    async def _refused(*_args, **_kwargs):
        raise ConnectionRefusedError("nope")

    monkeypatch.setattr(asyncio, "open_connection", _refused)
    assert asyncio.run(_qmd_health_check()) is False


def test_dashboard_restart_fails_when_running_without_pid(temp_abyss_home, monkeypatch):
    """If the dashboard is detected via port fallback (no PID file), the
    restart command must surface a non-zero exit instead of silently
    handing off to dashboard_start (which would no-op as 'already running')."""
    from abyss import cli

    # Simulate "running but PID unknown".
    monkeypatch.setattr(cli, "_is_dashboard_running", lambda: (True, None))
    monkeypatch.setattr(cli, "_get_dashboard_port", lambda: cli.DASHBOARD_DEFAULT_PORT)

    # If dashboard_start is reached, the test fails — restart must short-circuit.
    def _explode(*_args, **_kwargs):
        raise AssertionError("dashboard_start should not be called when PID is missing")

    monkeypatch.setattr(cli, "dashboard_start", _explode)

    result = runner.invoke(app, ["dashboard", "restart"])
    assert result.exit_code == 1
    assert "no PID is tracked" in result.stdout
