"""Tests for QMD builtin skill and daemon management."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml


@pytest.fixture()
def temp_cclaw_home(tmp_path, monkeypatch):
    """Set up a temporary cclaw home directory."""
    monkeypatch.setenv("CCLAW_HOME", str(tmp_path))
    return tmp_path


# --- Builtin Skill Registration ---


def test_qmd_in_builtin_skills_list():
    """QMD should appear in the built-in skills list."""
    from cclaw.builtin_skills import list_builtin_skills

    skills = list_builtin_skills()
    names = [s["name"] for s in skills]
    assert "qmd" in names


def test_qmd_builtin_skill_metadata():
    """QMD builtin skill should have correct metadata."""
    from cclaw.builtin_skills import get_builtin_skill_path

    path = get_builtin_skill_path("qmd")
    assert path is not None

    skill_yaml = path / "skill.yaml"
    assert skill_yaml.exists()

    with open(skill_yaml) as file:
        config = yaml.safe_load(file)

    assert config["name"] == "qmd"
    assert config["type"] == "mcp"
    assert "qmd" in config["required_commands"]
    assert "mcp__qmd__search" in config["allowed_tools"]
    assert "mcp__qmd__deep_search" in config["allowed_tools"]


def test_qmd_mcp_config_is_http_type():
    """QMD mcp.json should use HTTP transport, not stdio."""
    from cclaw.builtin_skills import get_builtin_skill_path

    path = get_builtin_skill_path("qmd")
    mcp_json = path / "mcp.json"
    assert mcp_json.exists()

    with open(mcp_json) as file:
        config = json.load(file)

    qmd_server = config["mcpServers"]["qmd"]
    assert qmd_server["type"] == "http"
    assert "url" in qmd_server
    assert "localhost" in qmd_server["url"]
    assert "/mcp" in qmd_server["url"]
    # Should NOT have command/args (those are for stdio)
    assert "command" not in qmd_server
    assert "args" not in qmd_server


# --- Skill Installation ---


def test_install_qmd_skill(temp_cclaw_home):
    """Installing QMD skill should copy all template files."""
    from cclaw.skill import install_builtin_skill

    path = install_builtin_skill("qmd")

    assert (path / "SKILL.md").exists()
    assert (path / "skill.yaml").exists()
    assert (path / "mcp.json").exists()

    # Verify MCP config was copied correctly
    with open(path / "mcp.json") as file:
        config = json.load(file)
    assert config["mcpServers"]["qmd"]["type"] == "http"


def test_install_qmd_skill_already_exists(temp_cclaw_home):
    """Installing QMD skill twice should raise FileExistsError."""
    from cclaw.skill import install_builtin_skill

    install_builtin_skill("qmd")
    with pytest.raises(FileExistsError):
        install_builtin_skill("qmd")


# --- MCP Config Merging ---


def test_qmd_mcp_config_merges(temp_cclaw_home):
    """QMD MCP config should merge correctly with other skills."""
    from cclaw.skill import install_builtin_skill, merge_mcp_configs

    install_builtin_skill("qmd")
    result = merge_mcp_configs(["qmd"])

    assert result is not None
    assert "mcpServers" in result
    assert "qmd" in result["mcpServers"]
    assert result["mcpServers"]["qmd"]["type"] == "http"


# --- Allowed Tools ---


def test_qmd_allowed_tools_collected(temp_cclaw_home):
    """QMD allowed tools should be collected correctly."""
    from cclaw.skill import collect_skill_allowed_tools, install_builtin_skill

    install_builtin_skill("qmd")
    tools = collect_skill_allowed_tools(["qmd"])

    assert "mcp__qmd__search" in tools
    assert "mcp__qmd__vector_search" in tools
    assert "mcp__qmd__deep_search" in tools
    assert "mcp__qmd__get" in tools
    assert "mcp__qmd__multi_get" in tools
    assert "mcp__qmd__status" in tools


# --- Auto-inject: claude_runner ---


def test_prepare_skill_config_injects_qmd_when_available(temp_cclaw_home):
    """QMD MCP should be auto-injected when qmd CLI is available."""
    import json

    from cclaw.claude_runner import _prepare_skill_config

    working_directory = str(temp_cclaw_home / "work")
    Path(working_directory).mkdir()

    with patch("shutil.which", return_value="/usr/local/bin/qmd"):
        allowed_tools, _ = _prepare_skill_config(working_directory, None)

    assert allowed_tools is not None
    assert "mcp__qmd__search" in allowed_tools
    assert "mcp__qmd__deep_search" in allowed_tools

    # Check .mcp.json was written with QMD config
    mcp_json = Path(working_directory) / ".mcp.json"
    assert mcp_json.exists()
    config = json.loads(mcp_json.read_text())
    assert "qmd" in config["mcpServers"]
    assert config["mcpServers"]["qmd"]["type"] == "http"


def test_prepare_skill_config_no_qmd_when_not_installed(temp_cclaw_home):
    """QMD should not be injected when qmd CLI is not available."""
    from cclaw.claude_runner import _prepare_skill_config

    working_directory = str(temp_cclaw_home / "work")
    Path(working_directory).mkdir()

    with patch("shutil.which", return_value=None):
        allowed_tools, _ = _prepare_skill_config(working_directory, None)

    assert allowed_tools is None


def test_prepare_skill_config_qmd_merges_with_skills(temp_cclaw_home):
    """QMD should merge with other skill MCP configs."""
    import json

    from cclaw.claude_runner import _prepare_skill_config
    from cclaw.skill import install_builtin_skill

    install_builtin_skill("supabase")

    working_directory = str(temp_cclaw_home / "work")
    Path(working_directory).mkdir()

    with patch("cclaw.claude_runner.shutil.which", return_value="/usr/local/bin/qmd"):
        allowed_tools, _ = _prepare_skill_config(working_directory, ["supabase"])

    assert allowed_tools is not None
    # Both supabase and qmd tools should be present
    assert "mcp__qmd__search" in allowed_tools
    assert "mcp__supabase__execute_sql" in allowed_tools

    # Check .mcp.json has both servers
    mcp_json = Path(working_directory) / ".mcp.json"
    config = json.loads(mcp_json.read_text())
    assert "qmd" in config["mcpServers"]
    assert "supabase" in config["mcpServers"]


# --- Auto-inject: compose_claude_md ---


def test_compose_claude_md_includes_qmd_when_available():
    """QMD instructions should be included in CLAUDE.md when CLI is available."""
    from cclaw.skill import compose_claude_md

    with patch("cclaw.skill.shutil.which", return_value="/usr/local/bin/qmd"):
        result = compose_claude_md("testbot", "friendly", "assistant")

    assert "qmd" in result.lower()
    assert "search" in result.lower()


def test_compose_claude_md_excludes_qmd_when_not_available():
    """QMD instructions should not be in CLAUDE.md when CLI is not available."""
    from cclaw.skill import compose_claude_md

    with patch("cclaw.skill.shutil.which", return_value=None):
        result = compose_claude_md("testbot", "friendly", "assistant")

    assert "qmd" not in result.lower()


# --- Bot Manager: QMD Daemon ---


@pytest.mark.asyncio
async def test_start_qmd_daemon_no_cli():
    """Should return False when qmd CLI is not found."""
    from cclaw.bot_manager import _start_qmd_daemon

    with patch("shutil.which", return_value=None):
        result = await _start_qmd_daemon()
    assert result is False


@pytest.mark.asyncio
async def test_start_qmd_daemon_already_running():
    """Should return True when daemon is already running."""
    from cclaw.bot_manager import _start_qmd_daemon

    with (
        patch("shutil.which", return_value="/usr/local/bin/qmd"),
        patch("cclaw.bot_manager._qmd_health_check", new_callable=AsyncMock, return_value=True),
    ):
        result = await _start_qmd_daemon()
    assert result is True


@pytest.mark.asyncio
async def test_start_qmd_daemon_starts_successfully():
    """Should start daemon and wait for health check."""
    from cclaw.bot_manager import _start_qmd_daemon

    health_call_count = 0

    async def mock_health():
        nonlocal health_call_count
        health_call_count += 1
        # Fail first time (not running), succeed second time (just started)
        return health_call_count >= 2

    with (
        patch("shutil.which", return_value="/usr/local/bin/qmd"),
        patch("cclaw.bot_manager._qmd_health_check", side_effect=mock_health),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value.returncode = 0
        result = await _start_qmd_daemon()

    assert result is True
    mock_run.assert_called_once_with(
        ["qmd", "mcp", "--http", "--daemon"],
        capture_output=True,
        text=True,
    )


@pytest.mark.asyncio
async def test_start_qmd_daemon_fails():
    """Should return False when daemon fails to start."""
    from cclaw.bot_manager import _start_qmd_daemon

    with (
        patch("shutil.which", return_value="/usr/local/bin/qmd"),
        patch("cclaw.bot_manager._qmd_health_check", new_callable=AsyncMock, return_value=False),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "error"
        result = await _start_qmd_daemon()

    assert result is False


def test_stop_qmd_daemon_calls_stop():
    """Should call 'qmd mcp stop' when stopping."""
    from cclaw.bot_manager import _stop_qmd_daemon

    with (
        patch("shutil.which", return_value="/usr/local/bin/qmd"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value.returncode = 0
        _stop_qmd_daemon()

    mock_run.assert_called_once_with(
        ["qmd", "mcp", "stop"],
        capture_output=True,
        text=True,
    )


def test_stop_qmd_daemon_no_cli():
    """Should do nothing when qmd CLI is not found."""
    from cclaw.bot_manager import _stop_qmd_daemon

    with (
        patch("shutil.which", return_value=None),
        patch("subprocess.run") as mock_run,
    ):
        _stop_qmd_daemon()

    mock_run.assert_not_called()


# --- Collection Setup ---


def test_ensure_qmd_conversations_collection(temp_cclaw_home):
    """Should register cclaw-conversations collection on start."""
    from cclaw.bot_manager import _ensure_qmd_conversations_collection

    (temp_cclaw_home / "bots" / "testbot" / "sessions").mkdir(parents=True)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        _ensure_qmd_conversations_collection()

    mock_run.assert_called_once()
    add_call = mock_run.call_args[0][0]
    assert "collection" in add_call
    assert "add" in add_call
    assert "cclaw-conversations" in add_call
    assert "**/conversation-*.md" in add_call


def test_ensure_qmd_conversations_no_bots_directory(temp_cclaw_home):
    """Should do nothing when bots directory doesn't exist."""
    from cclaw.bot_manager import _ensure_qmd_conversations_collection

    with patch("subprocess.run") as mock_run:
        _ensure_qmd_conversations_collection()

    mock_run.assert_not_called()


def test_setup_qmd_conversations_collection(temp_cclaw_home):
    """Should register cclaw-conversations collection via skill.py."""
    from cclaw.skill import setup_qmd_conversations_collection

    (temp_cclaw_home / "bots" / "testbot" / "sessions").mkdir(parents=True)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        result = setup_qmd_conversations_collection()

    assert result is True
    assert mock_run.call_count == 2

    add_call = mock_run.call_args_list[0]
    assert "cclaw-conversations" in add_call[0][0]


def test_setup_qmd_conversations_no_bots_directory(temp_cclaw_home):
    """Should return False when bots directory doesn't exist."""
    from cclaw.skill import setup_qmd_conversations_collection

    result = setup_qmd_conversations_collection()
    assert result is False
