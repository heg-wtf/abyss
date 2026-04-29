"""Tests for abyss.claude_runner module."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from abyss.claude_runner import (
    _extract_assistant_text,
    _extract_result_text,
    _extract_text_delta,
    _running_processes,
    _write_session_settings,
    cancel_all_processes,
    cancel_process,
    is_process_running,
    register_process,
    run_claude,
    run_claude_streaming,
    unregister_process,
)

MOCK_SUBPROCESS = "abyss.claude_runner.asyncio.create_subprocess_exec"
MOCK_WHICH = "abyss.claude_runner.shutil.which"


@pytest.fixture(autouse=True)
def mock_claude_path():
    """Mock shutil.which to always return a claude path and reset cache."""
    import abyss.claude_runner as runner_module

    def _which_claude_only(name, *args, **kwargs):
        if name == "claude":
            return "/usr/local/bin/claude"
        return None

    runner_module._cached_claude_path = None
    with patch(MOCK_WHICH, side_effect=_which_claude_only):
        yield
    runner_module._cached_claude_path = None


@pytest.mark.asyncio
async def test_run_claude_success():
    """run_claude returns stdout on success."""
    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"Hello from Claude", b""))
    mock_process.returncode = 0
    mock_process.kill = MagicMock()

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        result = await run_claude("/tmp/test", "Hello")

    assert result == "Hello from Claude"
    mock_exec.assert_called_once()
    call_args = mock_exec.call_args[0]
    assert any("claude" in str(arg) for arg in call_args)
    assert "-p" in call_args
    assert "Hello" in call_args


@pytest.mark.asyncio
async def test_run_claude_with_extra_arguments():
    """run_claude passes extra_arguments to command."""
    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"output", b""))
    mock_process.returncode = 0

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        await run_claude("/tmp/test", "Hello", extra_arguments=["--verbose"])

    call_args = mock_exec.call_args[0]
    assert "--verbose" in call_args


@pytest.mark.asyncio
async def test_run_claude_timeout():
    """run_claude raises TimeoutError on timeout."""
    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
    mock_process.kill = MagicMock()

    mock_process.communicate = AsyncMock(side_effect=[asyncio.TimeoutError(), (b"", b"")])

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process

        with patch(
            "abyss.claude_runner.asyncio.wait_for",
            side_effect=asyncio.TimeoutError(),
        ):
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            with pytest.raises(TimeoutError, match="timed out"):
                await run_claude("/tmp/test", "Hello", timeout=1)

    mock_process.kill.assert_called_once()


@pytest.mark.asyncio
async def test_run_claude_nonzero_exit():
    """run_claude raises RuntimeError on non-zero exit code."""
    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"", b"Error occurred"))
    mock_process.returncode = 1

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process

        with pytest.raises(RuntimeError, match="exited with code 1"):
            await run_claude("/tmp/test", "Hello")


@pytest.mark.asyncio
async def test_run_claude_working_directory():
    """run_claude uses the specified working directory."""
    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"ok", b""))
    mock_process.returncode = 0

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        await run_claude("/my/project", "Hello")

    call_kwargs = mock_exec.call_args[1]
    assert call_kwargs["cwd"] == "/my/project"


@pytest.mark.asyncio
async def test_run_claude_not_found():
    """run_claude raises RuntimeError when claude CLI is not found."""
    import abyss.claude_runner as runner_module

    runner_module._cached_claude_path = None
    with patch(MOCK_WHICH, return_value=None):
        with pytest.raises(RuntimeError, match="CLI not found"):
            await run_claude("/tmp/test", "Hello")


@pytest.mark.asyncio
async def test_run_claude_with_session_key_registers_process():
    """run_claude registers and unregisters process when session_key is provided."""
    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"output", b""))
    mock_process.returncode = 0

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        result = await run_claude("/tmp/test", "Hello", session_key="bot:123")

    assert result == "output"
    # Process should be unregistered after completion
    assert "bot:123" not in _running_processes


def test_register_and_unregister_process():
    """register_process and unregister_process manage the registry."""
    mock_process = MagicMock()
    register_process("test:1", mock_process)
    assert "test:1" in _running_processes

    unregister_process("test:1")
    assert "test:1" not in _running_processes

    # Unregister non-existent key should not raise
    unregister_process("test:nonexistent")


def test_cancel_process_running():
    """cancel_process kills a running process."""
    mock_process = MagicMock()
    mock_process.returncode = None  # Still running
    _running_processes["test:cancel"] = mock_process

    result = cancel_process("test:cancel")
    assert result is True
    mock_process.kill.assert_called_once()

    # Cleanup
    _running_processes.pop("test:cancel", None)


def test_cancel_process_not_running():
    """cancel_process returns False when no process is running."""
    result = cancel_process("test:nonexistent")
    assert result is False


def test_cancel_process_already_finished():
    """cancel_process returns False when process already finished."""
    mock_process = MagicMock()
    mock_process.returncode = 0  # Already finished
    _running_processes["test:finished"] = mock_process

    result = cancel_process("test:finished")
    assert result is False

    # Cleanup
    _running_processes.pop("test:finished", None)


def test_is_process_running_true():
    """is_process_running returns True for running process."""
    mock_process = MagicMock()
    mock_process.returncode = None
    _running_processes["test:running"] = mock_process

    assert is_process_running("test:running") is True

    # Cleanup
    _running_processes.pop("test:running", None)


def test_is_process_running_false():
    """is_process_running returns False when no process registered."""
    assert is_process_running("test:no") is False


@pytest.mark.asyncio
async def test_run_claude_cancelled_raises():
    """run_claude raises CancelledError when process is killed (returncode -9)."""
    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"", b""))
    mock_process.returncode = -9

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        with pytest.raises(asyncio.CancelledError, match="cancelled"):
            await run_claude("/tmp/test", "Hello", session_key="bot:cancel")


@pytest.mark.asyncio
async def test_run_claude_with_model():
    """run_claude passes --model flag when model is specified."""
    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"output", b""))
    mock_process.returncode = 0

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        await run_claude("/tmp/test", "Hello", model="opus")

    call_args = mock_exec.call_args[0]
    assert "--model" in call_args
    assert "opus" in call_args


@pytest.mark.asyncio
async def test_run_claude_without_model():
    """run_claude does not pass --model flag when model is None."""
    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"output", b""))
    mock_process.returncode = 0

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        await run_claude("/tmp/test", "Hello")

    call_args = mock_exec.call_args[0]
    assert "--model" not in call_args


@pytest.mark.asyncio
async def test_run_claude_with_skill_names_mcp(tmp_path):
    """run_claude writes .mcp.json when skills have MCP config."""
    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"output", b""))
    mock_process.returncode = 0

    mcp_config = {"mcpServers": {"test-server": {"command": "test"}}}

    with (
        patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec,
        patch(
            "abyss.skill.merge_mcp_configs",
            return_value=mcp_config,
        ),
        patch(
            "abyss.skill.collect_skill_environment_variables",
            return_value={},
        ),
    ):
        mock_exec.return_value = mock_process
        await run_claude(str(tmp_path), "Hello", skill_names=["test-skill"])

    import json

    mcp_json_path = tmp_path / ".mcp.json"
    assert mcp_json_path.exists()
    with open(mcp_json_path) as file:
        written_config = json.load(file)
    assert "test-server" in written_config["mcpServers"]


@pytest.mark.asyncio
async def test_run_claude_with_skill_names_env(tmp_path):
    """run_claude passes environment variables from skills."""
    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"output", b""))
    mock_process.returncode = 0

    with (
        patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec,
        patch("abyss.skill.merge_mcp_configs", return_value=None),
        patch(
            "abyss.skill.collect_skill_environment_variables",
            return_value={"API_KEY": "test-key"},
        ),
    ):
        mock_exec.return_value = mock_process
        await run_claude(str(tmp_path), "Hello", skill_names=["env-skill"])

    call_kwargs = mock_exec.call_args[1]
    assert call_kwargs["env"] is not None
    assert call_kwargs["env"]["API_KEY"] == "test-key"


@pytest.mark.asyncio
async def test_run_claude_with_allowed_tools(tmp_path):
    """run_claude passes --allowedTools when skills have allowed_tools."""
    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"output", b""))
    mock_process.returncode = 0

    with (
        patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec,
        patch("abyss.skill.merge_mcp_configs", return_value=None),
        patch("abyss.skill.collect_skill_environment_variables", return_value={}),
        patch(
            "abyss.skill.collect_skill_allowed_tools",
            return_value=["Bash(imsg:*)", "Read(*)"],
        ),
    ):
        mock_exec.return_value = mock_process
        await run_claude(str(tmp_path), "Hello", skill_names=["imessage"])

    call_args = mock_exec.call_args[0]
    assert "--allowedTools" in call_args
    allowed_index = list(call_args).index("--allowedTools")
    allowed_tools_value = call_args[allowed_index + 1]
    assert "Bash(imsg:*)" in allowed_tools_value
    assert "Read(*)" in allowed_tools_value
    # Default tools are always included when whitelist is active
    assert "WebFetch" in allowed_tools_value
    assert "WebSearch" in allowed_tools_value
    assert "Bash" in allowed_tools_value

    # Verify .claude/settings.json was created
    settings_path = tmp_path / ".claude" / "settings.json"
    assert settings_path.exists()
    with open(settings_path) as file:
        settings = json.load(file)
    assert "Bash(imsg:*)" in settings["permissions"]["allow"]
    assert "Read(*)" in settings["permissions"]["allow"]
    assert "WebFetch" in settings["permissions"]["allow"]


def test_write_session_settings_creates_file(tmp_path):
    """_write_session_settings creates .claude/settings.json with permissions."""
    _write_session_settings(str(tmp_path), ["Bash(reminders:*)", "Bash(osascript:*)"])

    settings_path = tmp_path / ".claude" / "settings.json"
    assert settings_path.exists()
    with open(settings_path) as file:
        settings = json.load(file)
    assert "Bash(reminders:*)" in settings["permissions"]["allow"]
    assert "Bash(osascript:*)" in settings["permissions"]["allow"]
    # Phase 3: hooks contains the abyss PreCompact entry
    assert "PreCompact" in settings["hooks"]
    assert settings["enabledPlugins"] == {}


def test_write_session_settings_blocks_inherited_hooks_with_clean_dict(tmp_path):
    """The hooks dict is clean-slate per session, blocking ~/.claude/settings.json
    entries except the keys abyss explicitly populates (PreCompact +
    PostToolUse + PostToolUseFailure)."""
    _write_session_settings(str(tmp_path), ["WebFetch"])

    settings_path = tmp_path / ".claude" / "settings.json"
    with open(settings_path) as file:
        settings = json.load(file)
    assert "hooks" in settings
    # Only abyss-controlled events are present. User globals (e.g. UserPromptSubmit,
    # SessionStart) cannot leak into the bot subprocess.
    assert set(settings["hooks"].keys()) == {
        "PreCompact",
        "PostToolUse",
        "PostToolUseFailure",
    }


def test_write_session_settings_disables_inherited_plugins(tmp_path):
    """_write_session_settings adds empty enabledPlugins to disable user plugins.

    Plugin hooks (e.g. context-mode) are loaded from ~/.claude/plugins/ and
    are NOT disabled by the hooks dict reset alone. Must also disable plugins.
    """
    _write_session_settings(str(tmp_path), ["WebFetch"])

    settings_path = tmp_path / ".claude" / "settings.json"
    with open(settings_path) as file:
        settings = json.load(file)
    assert "enabledPlugins" in settings
    assert settings["enabledPlugins"] == {}


def test_write_session_settings_preserves_existing_non_precompact_hooks(tmp_path):
    """Existing non-PreCompact hook entries are preserved; PreCompact is replaced."""
    claude_directory = tmp_path / ".claude"
    claude_directory.mkdir()
    existing = {
        "permissions": {"allow": []},
        "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": []}]},
        "enabledPlugins": {"some-plugin@marketplace": True},
    }
    with open(claude_directory / "settings.json", "w") as file:
        json.dump(existing, file)

    _write_session_settings(str(tmp_path), ["WebFetch"])

    with open(claude_directory / "settings.json") as file:
        settings = json.load(file)
    # Existing PreToolUse preserved
    assert settings["hooks"]["PreToolUse"] == [{"matcher": "Bash", "hooks": []}]
    # PreCompact added
    assert "PreCompact" in settings["hooks"]
    assert settings["enabledPlugins"] == {"some-plugin@marketplace": True}


def test_write_session_settings_merges_existing(tmp_path):
    """_write_session_settings merges with existing settings."""
    claude_directory = tmp_path / ".claude"
    claude_directory.mkdir()
    existing = {"permissions": {"allow": ["Read"]}}
    with open(claude_directory / "settings.json", "w") as file:
        json.dump(existing, file)

    _write_session_settings(str(tmp_path), ["Bash(reminders:*)"])

    with open(claude_directory / "settings.json") as file:
        settings = json.load(file)
    assert "Read" in settings["permissions"]["allow"]
    assert "Bash(reminders:*)" in settings["permissions"]["allow"]


def test_write_session_settings_empty_tools_writes_hook_only(tmp_path):
    """Empty tools still triggers settings.json creation (Phase 3) so the
    PreCompact hook can be installed for skill-less bots."""
    _write_session_settings(str(tmp_path), [])

    settings_path = tmp_path / ".claude" / "settings.json"
    assert settings_path.exists()
    with open(settings_path) as file:
        settings = json.load(file)
    # No permissions section when no tools.
    assert "permissions" not in settings
    # But hook is installed.
    assert "PreCompact" in settings["hooks"]


def test_write_session_settings_omits_precompact_when_bot_disables(tmp_path, monkeypatch):
    """When the resolved bot.yaml has hooks_enabled=false, PreCompact is not injected."""
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path / ".abyss"))

    from abyss.config import bot_directory, save_bot_config

    bot_name = "noisy"
    save_bot_config(
        bot_name,
        {
            "telegram_token": "fake",
            "personality": "x",
            "role": "y",
            "goal": "",
            "allowed_users": [],
            "claude_args": [],
            "hooks_enabled": False,
        },
    )

    session = bot_directory(bot_name) / "sessions" / "chat_1"
    session.mkdir(parents=True)

    _write_session_settings(str(session), ["WebFetch"])

    with open(session / ".claude" / "settings.json") as file:
        settings = json.load(file)
    assert "PreCompact" not in settings.get("hooks", {})


# --- Effort flag (Phase 6) ---


def test_effort_flag_args_returns_empty_when_no_bot_dir(tmp_path):
    from abyss.claude_runner import _effort_flag_args

    assert _effort_flag_args(str(tmp_path)) == []


def test_effort_flag_args_skips_when_bot_yaml_missing_field(tmp_path, monkeypatch):
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path / ".abyss"))

    from abyss.claude_runner import _effort_flag_args
    from abyss.config import bot_directory, save_bot_config

    save_bot_config(
        "alpha",
        {
            "telegram_token": "fake",
            "personality": "x",
            "role": "y",
            "goal": "",
            "allowed_users": [],
            "claude_args": [],
        },
    )
    session = bot_directory("alpha") / "sessions" / "chat_1"
    session.mkdir(parents=True)

    assert _effort_flag_args(str(session)) == []


def test_effort_flag_args_returns_flag_for_valid_level(tmp_path, monkeypatch):
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path / ".abyss"))

    from abyss.claude_runner import _effort_flag_args
    from abyss.config import bot_directory, save_bot_config

    save_bot_config(
        "alpha",
        {
            "telegram_token": "fake",
            "personality": "x",
            "role": "y",
            "goal": "",
            "allowed_users": [],
            "claude_args": [],
            "effort": "high",
        },
    )
    session = bot_directory("alpha") / "sessions" / "chat_1"
    session.mkdir(parents=True)

    assert _effort_flag_args(str(session)) == ["--effort", "high"]


def test_effort_flag_args_normalises_case_and_whitespace(tmp_path, monkeypatch):
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path / ".abyss"))

    from abyss.claude_runner import _effort_flag_args
    from abyss.config import bot_directory, save_bot_config

    save_bot_config(
        "alpha",
        {
            "telegram_token": "fake",
            "personality": "x",
            "role": "y",
            "goal": "",
            "allowed_users": [],
            "claude_args": [],
            "effort": "  Xhigh  ",
        },
    )
    session = bot_directory("alpha") / "sessions" / "chat_1"
    session.mkdir(parents=True)

    assert _effort_flag_args(str(session)) == ["--effort", "xhigh"]


def test_effort_flag_args_drops_invalid_level(tmp_path, monkeypatch):
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path / ".abyss"))

    from abyss.claude_runner import _effort_flag_args
    from abyss.config import bot_directory, save_bot_config

    save_bot_config(
        "alpha",
        {
            "telegram_token": "fake",
            "personality": "x",
            "role": "y",
            "goal": "",
            "allowed_users": [],
            "claude_args": [],
            "effort": "ultra",  # not a valid CC level
        },
    )
    session = bot_directory("alpha") / "sessions" / "chat_1"
    session.mkdir(parents=True)

    assert _effort_flag_args(str(session)) == []


@pytest.mark.asyncio
async def test_run_claude_passes_effort_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path / ".abyss"))

    from abyss.config import bot_directory, save_bot_config

    save_bot_config(
        "alpha",
        {
            "telegram_token": "fake",
            "personality": "x",
            "role": "y",
            "goal": "",
            "allowed_users": [],
            "claude_args": [],
            "effort": "max",
        },
    )
    session = bot_directory("alpha") / "sessions" / "chat_1"
    session.mkdir(parents=True)

    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"ok", b""))
    mock_process.returncode = 0

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        await run_claude(str(session), "Hello")

    args = list(mock_exec.call_args[0])
    assert "--effort" in args
    assert args[args.index("--effort") + 1] == "max"


# --- run_ultrareview (Phase 6) ---


@pytest.mark.asyncio
async def test_run_ultrareview_invokes_subcommand(tmp_path):
    from abyss.claude_runner import run_ultrareview

    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b'{"findings": []}', b""))
    mock_process.returncode = 0

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        result = await run_ultrareview("https://github.com/x/y/pull/1", str(tmp_path))

    args = list(mock_exec.call_args[0])
    assert "ultrareview" in args
    assert "https://github.com/x/y/pull/1" in args
    assert "--json" in args
    assert result == '{"findings": []}'


@pytest.mark.asyncio
async def test_run_ultrareview_drops_json_when_disabled(tmp_path):
    from abyss.claude_runner import run_ultrareview

    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"text report", b""))
    mock_process.returncode = 0

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        await run_ultrareview("123", str(tmp_path), json_output=False)

    args = list(mock_exec.call_args[0])
    assert "--json" not in args


@pytest.mark.asyncio
async def test_run_ultrareview_passes_extra_arguments(tmp_path):
    from abyss.claude_runner import run_ultrareview

    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"ok", b""))
    mock_process.returncode = 0

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        await run_ultrareview(
            "123",
            str(tmp_path),
            extra_arguments=["--timeout", "10"],
        )

    args = list(mock_exec.call_args[0])
    assert "--timeout" in args
    assert "10" in args


@pytest.mark.asyncio
async def test_run_ultrareview_raises_on_nonzero_exit(tmp_path):
    from abyss.claude_runner import run_ultrareview

    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"", b"boom"))
    mock_process.returncode = 1

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        with pytest.raises(RuntimeError, match="ultrareview exited"):
            await run_ultrareview("123", str(tmp_path))


@pytest.mark.asyncio
async def test_run_ultrareview_rejects_empty_target(tmp_path):
    from abyss.claude_runner import run_ultrareview

    with pytest.raises(ValueError):
        await run_ultrareview("", str(tmp_path))
    with pytest.raises(ValueError):
        await run_ultrareview("   ", str(tmp_path))


@pytest.mark.asyncio
async def test_run_ultrareview_timeout(tmp_path):
    from abyss.claude_runner import run_ultrareview

    mock_process = MagicMock()
    mock_process.kill = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"", b""))

    with (
        patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec,
        patch(
            "abyss.claude_runner.asyncio.wait_for",
            side_effect=asyncio.TimeoutError(),
        ),
    ):
        mock_exec.return_value = mock_process
        with pytest.raises(TimeoutError, match="ultrareview timed out"):
            await run_ultrareview("123", str(tmp_path), timeout=5)

    mock_process.kill.assert_called_once()


def test_write_session_settings_includes_default_sandbox(tmp_path):
    """Phase 5: every session.json carries the abyss default deniedDomains."""
    _write_session_settings(str(tmp_path), ["WebFetch"])
    with open(tmp_path / ".claude" / "settings.json") as file:
        settings = json.load(file)

    domains = settings["sandbox"]["network"]["deniedDomains"]
    assert "metadata.google.internal" in domains
    assert "169.254.169.254" in domains


def test_write_session_settings_merges_bot_sandbox_extras(tmp_path, monkeypatch):
    """bot.yaml.sandbox.denied_domains is merged on top of defaults."""
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path / ".abyss"))

    from abyss.config import bot_directory, save_bot_config

    save_bot_config(
        "alpha",
        {
            "telegram_token": "fake",
            "personality": "x",
            "role": "y",
            "goal": "",
            "allowed_users": [],
            "claude_args": [],
            "sandbox": {"denied_domains": ["sensitive.example.com"]},
        },
    )
    session = bot_directory("alpha") / "sessions" / "chat_1"
    session.mkdir(parents=True)

    _write_session_settings(str(session), ["WebFetch"])
    with open(session / ".claude" / "settings.json") as file:
        settings = json.load(file)

    domains = settings["sandbox"]["network"]["deniedDomains"]
    assert domains[0] == "metadata.google.internal"
    assert "sensitive.example.com" in domains


def test_write_session_settings_disables_skill_shell_when_untrusted(tmp_path, monkeypatch):
    """Attaching an untrusted skill flips disableSkillShellExecution=true."""
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path / ".abyss"))

    import yaml

    from abyss.config import bot_directory, save_bot_config
    from abyss.skill import skill_directory

    skill_path = skill_directory("imported")
    skill_path.mkdir(parents=True)
    (skill_path / "SKILL.md").write_text("# imported\n")
    (skill_path / "skill.yaml").write_text(yaml.safe_dump({"untrusted": True}))

    save_bot_config(
        "alpha",
        {
            "telegram_token": "fake",
            "personality": "x",
            "role": "y",
            "goal": "",
            "allowed_users": [],
            "claude_args": [],
            "skills": ["imported"],
        },
    )

    session = bot_directory("alpha") / "sessions" / "chat_1"
    session.mkdir(parents=True)

    _write_session_settings(str(session), ["WebFetch"])
    with open(session / ".claude" / "settings.json") as file:
        settings = json.load(file)

    assert settings["disableSkillShellExecution"] is True


def test_write_session_settings_keeps_skill_shell_enabled_for_trusted_skills(tmp_path, monkeypatch):
    """No untrusted skill -> disableSkillShellExecution=false."""
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path / ".abyss"))

    from abyss.config import bot_directory, save_bot_config
    from abyss.skill import skill_directory

    skill_path = skill_directory("safe")
    skill_path.mkdir(parents=True)
    (skill_path / "SKILL.md").write_text("# safe\n")

    save_bot_config(
        "alpha",
        {
            "telegram_token": "fake",
            "personality": "x",
            "role": "y",
            "goal": "",
            "allowed_users": [],
            "claude_args": [],
            "skills": ["safe"],
        },
    )

    session = bot_directory("alpha") / "sessions" / "chat_1"
    session.mkdir(parents=True)

    _write_session_settings(str(session), ["WebFetch"])
    with open(session / ".claude" / "settings.json") as file:
        settings = json.load(file)

    assert settings["disableSkillShellExecution"] is False


def test_write_session_settings_command_uses_python_module(tmp_path):
    """The PreCompact hook command points at ``python -m abyss.hooks.precompact_hook``."""
    import sys

    _write_session_settings(str(tmp_path), ["WebFetch"])
    with open(tmp_path / ".claude" / "settings.json") as file:
        settings = json.load(file)

    entries = settings["hooks"]["PreCompact"]
    assert len(entries) == 1
    inner = entries[0]["hooks"][0]
    assert inner["type"] == "command"
    assert inner["command"] == f"{sys.executable} -m abyss.hooks.precompact_hook"


def test_write_session_settings_injects_post_tool_use(tmp_path):
    """PostToolUse hook is registered for tool latency metrics with outcome=success."""
    import sys

    _write_session_settings(str(tmp_path), ["WebFetch"])
    with open(tmp_path / ".claude" / "settings.json") as file:
        settings = json.load(file)

    entries = settings["hooks"]["PostToolUse"]
    assert len(entries) == 1
    assert entries[0]["matcher"] == "*"
    inner = entries[0]["hooks"][0]
    assert inner["type"] == "command"
    assert "ABYSS_HOOK_OUTCOME=success" in inner["command"]
    assert f"{sys.executable} -m abyss.hooks.log_tool_metrics" in inner["command"]


def test_write_session_settings_injects_post_tool_use_failure(tmp_path):
    """PostToolUseFailure hook is registered separately (CC fires the
    failure channel for non-zero tool exits / exceptions; PostToolUse is
    success-only). The hook command tags the event with outcome=failure
    via ABYSS_HOOK_OUTCOME."""
    import sys

    _write_session_settings(str(tmp_path), ["WebFetch"])
    with open(tmp_path / ".claude" / "settings.json") as file:
        settings = json.load(file)

    entries = settings["hooks"]["PostToolUseFailure"]
    assert len(entries) == 1
    assert entries[0]["matcher"] == "*"
    inner = entries[0]["hooks"][0]
    assert "ABYSS_HOOK_OUTCOME=failure" in inner["command"]
    assert f"{sys.executable} -m abyss.hooks.log_tool_metrics" in inner["command"]


def test_write_session_settings_omits_post_tool_use_when_bot_disables(tmp_path, monkeypatch):
    """`hooks_enabled: false` skips PostToolUse along with PreCompact."""
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path / ".abyss"))

    from abyss.config import bot_directory, save_bot_config

    save_bot_config(
        "noisy",
        {
            "telegram_token": "fake",
            "personality": "x",
            "role": "y",
            "goal": "",
            "allowed_users": [],
            "claude_args": [],
            "hooks_enabled": False,
        },
    )
    session = bot_directory("noisy") / "sessions" / "chat_1"
    session.mkdir(parents=True)

    _write_session_settings(str(session), ["WebFetch"])
    with open(session / ".claude" / "settings.json") as file:
        settings = json.load(file)
    assert "PreCompact" not in settings["hooks"]
    assert "PostToolUse" not in settings["hooks"]
    assert "PostToolUseFailure" not in settings["hooks"]


def test_write_session_settings_appends_skill_post_tool_use_hooks(tmp_path, monkeypatch):
    """Skill-declared PostToolUse hooks are appended after the abyss baseline."""
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path / ".abyss"))

    import yaml

    from abyss.config import bot_directory, save_bot_config
    from abyss.skill import skill_directory

    skill_path = skill_directory("safety")
    skill_path.mkdir(parents=True)
    (skill_path / "SKILL.md").write_text("# safety\nGuardrail.")
    skill_yaml = {
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "Bash",
                    "if": "tool_input.command =~ /rm -rf/",
                    "hooks": [{"type": "command", "command": "/usr/local/bin/safety-check.sh"}],
                }
            ]
        }
    }
    (skill_path / "skill.yaml").write_text(yaml.safe_dump(skill_yaml))

    save_bot_config(
        "alpha",
        {
            "telegram_token": "fake",
            "personality": "x",
            "role": "y",
            "goal": "",
            "allowed_users": [],
            "claude_args": [],
            "skills": ["safety"],
        },
    )

    session = bot_directory("alpha") / "sessions" / "chat_1"
    session.mkdir(parents=True)

    _write_session_settings(str(session), ["WebFetch"])
    with open(session / ".claude" / "settings.json") as file:
        settings = json.load(file)

    post_entries = settings["hooks"]["PostToolUse"]
    # First: abyss baseline. Second: skill-supplied with `if` field.
    assert len(post_entries) == 2
    assert post_entries[0]["matcher"] == "*"
    assert post_entries[1]["matcher"] == "Bash"
    assert post_entries[1]["if"] == "tool_input.command =~ /rm -rf/"


@pytest.mark.asyncio
async def test_run_claude_without_skill_names():
    """run_claude returns env=None when working_directory does not exist."""
    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"output", b""))
    mock_process.returncode = 0

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        # /tmp/does-not-exist-xyz triggers the early-return branch in
        # _prepare_skill_config, so no env is composed.
        await run_claude("/tmp/does-not-exist-xyz-abyss", "Hello", skill_names=None)

    call_kwargs = mock_exec.call_args[1]
    assert call_kwargs["env"] is None


@pytest.mark.asyncio
async def test_run_claude_injects_claude_code_env_without_skills(tmp_path, monkeypatch):
    """Claude Code env vars are injected even when no skills are attached."""
    # Use temp ABYSS_HOME so config defaults apply (all toggles on).
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path / ".abyss"))

    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"output", b""))
    mock_process.returncode = 0

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        await run_claude(str(tmp_path), "Hello", skill_names=None)

    call_kwargs = mock_exec.call_args[1]
    env = call_kwargs["env"]
    assert env is not None
    assert env["AI_AGENT"] == "abyss"
    assert env["ENABLE_PROMPT_CACHING_1H"] == "1"
    assert env["CLAUDE_CODE_FORK_SUBAGENT"] == "1"
    assert env["MCP_CONNECTION_NONBLOCKING"] == "true"
    assert env["CLAUDE_CODE_HIDE_CWD"] == "1"


@pytest.mark.asyncio
async def test_run_claude_skill_env_overrides_claude_code_env(tmp_path, monkeypatch):
    """Skill env vars take precedence on key collision."""
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path / ".abyss"))

    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"output", b""))
    mock_process.returncode = 0

    with (
        patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec,
        patch("abyss.skill.merge_mcp_configs", return_value=None),
        patch(
            "abyss.skill.collect_skill_environment_variables",
            return_value={"AI_AGENT": "custom-skill"},
        ),
    ):
        mock_exec.return_value = mock_process
        await run_claude(str(tmp_path), "Hello", skill_names=["override-skill"])

    env = mock_exec.call_args[1]["env"]
    assert env["AI_AGENT"] == "custom-skill"
    # Other Claude Code env still injected
    assert env["ENABLE_PROMPT_CACHING_1H"] == "1"


@pytest.mark.asyncio
async def test_run_claude_disabled_toggle_strips_host_env(tmp_path, monkeypatch):
    """Disabled toggle removes a host-shell export from the subprocess env."""
    abyss_home = tmp_path / ".abyss"
    monkeypatch.setenv("ABYSS_HOME", str(abyss_home))

    # Simulate a user shell profile setting the var on the host.
    monkeypatch.setenv("ENABLE_PROMPT_CACHING_1H", "1")

    # Disable the toggle in config.yaml.
    from abyss.config import default_config, save_config

    config = default_config()
    config["claude_code"]["prompt_caching_1h"] = False
    save_config(config)

    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"output", b""))
    mock_process.returncode = 0

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        await run_claude(str(tmp_path), "Hello", skill_names=None)

    env = mock_exec.call_args[1]["env"]
    assert "ENABLE_PROMPT_CACHING_1H" not in env


# --- Streaming helper tests ---


def test_extract_text_delta_valid():
    """_extract_text_delta extracts text from stream_event content_block_delta."""
    data = {
        "type": "stream_event",
        "event": {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "Hello"},
        },
    }
    assert _extract_text_delta(data) == "Hello"


def test_extract_text_delta_wrong_type():
    """_extract_text_delta returns None for non-stream_event."""
    assert _extract_text_delta({"type": "result"}) is None


def test_extract_text_delta_wrong_delta_type():
    """_extract_text_delta returns None for non-text_delta."""
    data = {
        "type": "stream_event",
        "event": {
            "type": "content_block_delta",
            "delta": {"type": "input_json_delta", "partial_json": "{}"},
        },
    }
    assert _extract_text_delta(data) is None


def test_extract_result_text_valid():
    """_extract_result_text extracts text from result event."""
    data = {"type": "result", "subtype": "success", "result": "Final answer"}
    assert _extract_result_text(data) == "Final answer"


def test_extract_result_text_wrong_type():
    """_extract_result_text returns None for non-result event."""
    assert _extract_result_text({"type": "assistant"}) is None


def test_extract_assistant_text_valid():
    """_extract_assistant_text extracts text from assistant turn event."""
    data = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "text", "text": "Hello "},
                {"type": "text", "text": "world"},
            ]
        },
    }
    assert _extract_assistant_text(data) == "Hello world"


def test_extract_assistant_text_no_text_blocks():
    """_extract_assistant_text returns None when no text blocks."""
    data = {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": "bash"}]},
    }
    assert _extract_assistant_text(data) is None


def test_extract_assistant_text_wrong_type():
    """_extract_assistant_text returns None for non-assistant event."""
    assert _extract_assistant_text({"type": "result"}) is None


# --- run_claude_streaming tests ---


@pytest.mark.asyncio
async def test_run_claude_streaming_with_result_event():
    """run_claude_streaming returns result event text when available."""
    delta_hello = (
        b'{"type":"stream_event","event":{"type":"content_block_delta",'
        b'"index":0,"delta":{"type":"text_delta","text":"Hello"}}}\n'
    )
    delta_world = (
        b'{"type":"stream_event","event":{"type":"content_block_delta",'
        b'"index":0,"delta":{"type":"text_delta","text":" world"}}}\n'
    )
    result_line = b'{"type":"result","subtype":"success","result":"Hello world"}\n'
    stream_lines = [delta_hello, delta_world, result_line]

    mock_stdout = AsyncMock()
    line_index = 0

    async def mock_readline():
        nonlocal line_index
        if line_index < len(stream_lines):
            line = stream_lines[line_index]
            line_index += 1
            return line
        return b""

    mock_stdout.readline = mock_readline

    mock_stderr = AsyncMock()
    mock_stderr.read = AsyncMock(return_value=b"")

    mock_process = MagicMock()
    mock_process.stdout = mock_stdout
    mock_process.stderr = mock_stderr
    mock_process.returncode = 0
    mock_process.wait = AsyncMock()

    chunks = []

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        result = await run_claude_streaming(
            "/tmp/test", "Hello", on_text_chunk=lambda c: chunks.append(c)
        )

    assert result == "Hello world"
    assert chunks == ["Hello", " world"]


@pytest.mark.asyncio
async def test_run_claude_streaming_fallback_to_accumulated():
    """run_claude_streaming falls back to accumulated text when no result event."""
    delta_fallback = (
        b'{"type":"stream_event","event":{"type":"content_block_delta",'
        b'"index":0,"delta":{"type":"text_delta","text":"Fallback"}}}\n'
    )
    delta_text = (
        b'{"type":"stream_event","event":{"type":"content_block_delta",'
        b'"index":0,"delta":{"type":"text_delta","text":" text"}}}\n'
    )
    stream_lines = [delta_fallback, delta_text]

    mock_stdout = AsyncMock()
    line_index = 0

    async def mock_readline():
        nonlocal line_index
        if line_index < len(stream_lines):
            line = stream_lines[line_index]
            line_index += 1
            return line
        return b""

    mock_stdout.readline = mock_readline

    mock_stderr = AsyncMock()
    mock_stderr.read = AsyncMock(return_value=b"")

    mock_process = MagicMock()
    mock_process.stdout = mock_stdout
    mock_process.stderr = mock_stderr
    mock_process.returncode = 0
    mock_process.wait = AsyncMock()

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        result = await run_claude_streaming("/tmp/test", "Hello")

    assert result == "Fallback text"


@pytest.mark.asyncio
async def test_run_claude_streaming_command_flags():
    """run_claude_streaming uses stream-json, --verbose, --include-partial-messages."""
    mock_stdout = AsyncMock()
    mock_stdout.readline = AsyncMock(return_value=b"")

    mock_stderr = AsyncMock()
    mock_stderr.read = AsyncMock(return_value=b"")

    mock_process = MagicMock()
    mock_process.stdout = mock_stdout
    mock_process.stderr = mock_stderr
    mock_process.returncode = 0
    mock_process.wait = AsyncMock()

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        await run_claude_streaming("/tmp/test", "Hello")

    call_args = mock_exec.call_args[0]
    assert "stream-json" in call_args
    assert "--verbose" in call_args
    assert "--include-partial-messages" in call_args


@pytest.mark.asyncio
async def test_run_claude_streaming_cancelled():
    """run_claude_streaming raises CancelledError when killed."""
    mock_stdout = AsyncMock()
    mock_stdout.readline = AsyncMock(return_value=b"")

    mock_stderr = AsyncMock()
    mock_stderr.read = AsyncMock(return_value=b"")

    mock_process = MagicMock()
    mock_process.stdout = mock_stdout
    mock_process.stderr = mock_stderr
    mock_process.returncode = -9
    mock_process.wait = AsyncMock()

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        with pytest.raises(asyncio.CancelledError, match="cancelled"):
            await run_claude_streaming("/tmp/test", "Hello", session_key="bot:123")


@pytest.mark.asyncio
async def test_run_claude_streaming_with_model():
    """run_claude_streaming passes --model flag."""
    mock_stdout = AsyncMock()
    mock_stdout.readline = AsyncMock(return_value=b"")

    mock_stderr = AsyncMock()
    mock_stderr.read = AsyncMock(return_value=b"")

    mock_process = MagicMock()
    mock_process.stdout = mock_stdout
    mock_process.stderr = mock_stderr
    mock_process.returncode = 0
    mock_process.wait = AsyncMock()

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        await run_claude_streaming("/tmp/test", "Hello", model="haiku")

    call_args = mock_exec.call_args[0]
    assert "--model" in call_args
    assert "haiku" in call_args


@pytest.mark.asyncio
async def test_run_claude_streaming_assistant_fallback():
    """run_claude_streaming falls back to assistant turn text."""
    assistant_line = (
        b'{"type":"assistant","message":{"content":'
        b'[{"type":"text","text":"Assistant response"}]}}\n'
    )
    stream_lines = [assistant_line]

    mock_stdout = AsyncMock()
    line_index = 0

    async def mock_readline():
        nonlocal line_index
        if line_index < len(stream_lines):
            line = stream_lines[line_index]
            line_index += 1
            return line
        return b""

    mock_stdout.readline = mock_readline

    mock_stderr = AsyncMock()
    mock_stderr.read = AsyncMock(return_value=b"")

    mock_process = MagicMock()
    mock_process.stdout = mock_stdout
    mock_process.stderr = mock_stderr
    mock_process.returncode = 0
    mock_process.wait = AsyncMock()

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        result = await run_claude_streaming("/tmp/test", "Hello")

    assert result == "Assistant response"


@pytest.mark.asyncio
async def test_run_claude_streaming_with_allowed_tools(tmp_path):
    """run_claude_streaming passes --allowedTools when skills have allowed_tools."""
    mock_stdout = AsyncMock()
    mock_stdout.readline = AsyncMock(return_value=b"")

    mock_stderr = AsyncMock()
    mock_stderr.read = AsyncMock(return_value=b"")

    mock_process = MagicMock()
    mock_process.stdout = mock_stdout
    mock_process.stderr = mock_stderr
    mock_process.returncode = 0
    mock_process.wait = AsyncMock()

    with (
        patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec,
        patch(
            "abyss.claude_runner._prepare_skill_config",
            return_value=(["Bash(imsg:*)"], None),
        ),
    ):
        mock_exec.return_value = mock_process
        await run_claude_streaming(str(tmp_path), "Hello", skill_names=["imessage"])

    call_args = mock_exec.call_args[0]
    assert "--allowedTools" in call_args
    allowed_index = list(call_args).index("--allowedTools")
    assert call_args[allowed_index + 1] == "Bash(imsg:*)"


# --- Session continuity tests ---


@pytest.mark.asyncio
async def test_run_claude_with_resume_session():
    """run_claude uses --resume when resume_session=True and session_id is given."""
    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"output", b""))
    mock_process.returncode = 0

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        await run_claude(
            "/tmp/test",
            "Hello",
            claude_session_id="session-abc-123",
            resume_session=True,
        )

    call_args = mock_exec.call_args[0]
    assert "--resume" in call_args
    assert "session-abc-123" in call_args
    assert "--session-id" not in call_args


@pytest.mark.asyncio
async def test_run_claude_with_session_id_no_resume():
    """run_claude uses --session-id when resume_session=False and session_id is given."""
    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"output", b""))
    mock_process.returncode = 0

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        await run_claude(
            "/tmp/test",
            "Hello",
            claude_session_id="session-abc-123",
            resume_session=False,
        )

    call_args = mock_exec.call_args[0]
    assert "--session-id" in call_args
    assert "session-abc-123" in call_args
    assert "--resume" not in call_args


@pytest.mark.asyncio
async def test_run_claude_no_session_id():
    """run_claude uses neither --resume nor --session-id when no session_id."""
    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"output", b""))
    mock_process.returncode = 0

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        await run_claude("/tmp/test", "Hello")

    call_args = mock_exec.call_args[0]
    assert "--resume" not in call_args
    assert "--session-id" not in call_args


@pytest.mark.asyncio
async def test_run_claude_streaming_with_resume_session():
    """run_claude_streaming uses --resume when resume_session=True."""
    mock_stdout = AsyncMock()
    mock_stdout.readline = AsyncMock(return_value=b"")

    mock_stderr = AsyncMock()
    mock_stderr.read = AsyncMock(return_value=b"")

    mock_process = MagicMock()
    mock_process.stdout = mock_stdout
    mock_process.stderr = mock_stderr
    mock_process.returncode = 0
    mock_process.wait = AsyncMock()

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        await run_claude_streaming(
            "/tmp/test",
            "Hello",
            claude_session_id="stream-session-123",
            resume_session=True,
        )

    call_args = mock_exec.call_args[0]
    assert "--resume" in call_args
    assert "stream-session-123" in call_args
    assert "--session-id" not in call_args


@pytest.mark.asyncio
async def test_run_claude_streaming_with_session_id_no_resume():
    """run_claude_streaming uses --session-id when resume_session=False."""
    mock_stdout = AsyncMock()
    mock_stdout.readline = AsyncMock(return_value=b"")

    mock_stderr = AsyncMock()
    mock_stderr.read = AsyncMock(return_value=b"")

    mock_process = MagicMock()
    mock_process.stdout = mock_stdout
    mock_process.stderr = mock_stderr
    mock_process.returncode = 0
    mock_process.wait = AsyncMock()

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        await run_claude_streaming(
            "/tmp/test",
            "Hello",
            claude_session_id="stream-session-123",
            resume_session=False,
        )

    call_args = mock_exec.call_args[0]
    assert "--session-id" in call_args
    assert "stream-session-123" in call_args
    assert "--resume" not in call_args


# --- cancel_all_processes tests ---


def test_cancel_all_processes_kills_running():
    """cancel_all_processes kills all running processes and clears registry."""
    process_a = MagicMock()
    process_a.returncode = None  # Running
    process_b = MagicMock()
    process_b.returncode = None  # Running

    _running_processes["bot:1"] = process_a
    _running_processes["bot:2"] = process_b

    killed = cancel_all_processes()

    assert killed == 2
    process_a.kill.assert_called_once()
    process_b.kill.assert_called_once()
    assert len(_running_processes) == 0


def test_cancel_all_processes_skips_finished():
    """cancel_all_processes skips already-finished processes."""
    running = MagicMock()
    running.returncode = None
    finished = MagicMock()
    finished.returncode = 0

    _running_processes["bot:run"] = running
    _running_processes["bot:done"] = finished

    killed = cancel_all_processes()

    assert killed == 1
    running.kill.assert_called_once()
    finished.kill.assert_not_called()
    assert len(_running_processes) == 0


def test_cancel_all_processes_empty():
    """cancel_all_processes returns 0 when no processes registered."""
    _running_processes.clear()
    killed = cancel_all_processes()
    assert killed == 0


# --- SDK-aware runner tests ---


class TestSDKAwareRunner:
    @pytest.mark.asyncio
    async def test_run_with_sdk_pool_success(self, tmp_path):
        """Uses SDK pool when available."""
        from abyss.claude_runner import run_claude_with_sdk
        from abyss.sdk_client import SDKClientPool, SDKQueryResult

        mock_result = SDKQueryResult(text="pool response", session_id="sess-1")
        mock_pool = MagicMock(spec=SDKClientPool)
        mock_pool.has_session.return_value = False
        mock_pool.query = AsyncMock(return_value=mock_result)

        with (
            patch("abyss.sdk_client.is_sdk_available", return_value=True),
            patch("abyss.sdk_client.get_pool", return_value=mock_pool),
        ):
            result = await run_claude_with_sdk(
                working_directory=str(tmp_path),
                message="hello",
                session_key="bot1:chat_1",
            )

        assert result == "pool response"
        mock_pool.query.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_with_sdk_pool_saves_session_id(self, tmp_path):
        """Pool result session_id is saved to session_directory."""
        from abyss.claude_runner import run_claude_with_sdk
        from abyss.sdk_client import SDKClientPool, SDKQueryResult

        session_dir = tmp_path / "session"
        session_dir.mkdir()

        mock_result = SDKQueryResult(text="ok", session_id="new-sess-123")
        mock_pool = MagicMock(spec=SDKClientPool)
        mock_pool.has_session.return_value = False
        mock_pool.query = AsyncMock(return_value=mock_result)

        with (
            patch("abyss.sdk_client.is_sdk_available", return_value=True),
            patch("abyss.sdk_client.get_pool", return_value=mock_pool),
        ):
            await run_claude_with_sdk(
                working_directory=str(tmp_path),
                message="hello",
                session_key="bot1:chat_1",
                session_directory=session_dir,
            )

        saved_id = (session_dir / ".claude_session_id").read_text().strip()
        assert saved_id == "new-sess-123"

    @pytest.mark.asyncio
    async def test_run_with_sdk_fallback_when_unavailable(self, tmp_path):
        """Falls back to subprocess when SDK is not available."""
        from abyss.claude_runner import run_claude_with_sdk

        with (
            patch("abyss.sdk_client.is_sdk_available", return_value=False),
            patch("abyss.claude_runner.run_claude", new_callable=AsyncMock) as mock_run,
        ):
            mock_run.return_value = "subprocess response"
            result = await run_claude_with_sdk(
                working_directory=str(tmp_path),
                message="hello",
                session_key="bot1:chat_1",
                claude_session_id="sess-1",
                resume_session=True,
            )

        assert result == "subprocess response"
        mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_with_sdk_pool_error_falls_back(self, tmp_path):
        """Falls back to subprocess when pool query fails."""
        from abyss.claude_runner import run_claude_with_sdk
        from abyss.sdk_client import SDKClientPool

        mock_pool = MagicMock(spec=SDKClientPool)
        mock_pool.has_session.return_value = False
        mock_pool.query = AsyncMock(side_effect=RuntimeError("pool error"))
        mock_pool.close_session = AsyncMock()

        with (
            patch("abyss.sdk_client.is_sdk_available", return_value=True),
            patch("abyss.sdk_client.get_pool", return_value=mock_pool),
            patch("abyss.claude_runner.run_claude", new_callable=AsyncMock) as mock_run,
        ):
            mock_run.return_value = "fallback response"
            result = await run_claude_with_sdk(
                working_directory=str(tmp_path),
                message="hello",
                session_key="bot1:chat_1",
            )

        assert result == "fallback response"
        mock_run.assert_called_once()
        mock_pool.close_session.assert_called_once_with("bot1:chat_1")

    @pytest.mark.asyncio
    async def test_run_with_sdk_no_session_key_uses_subprocess(self, tmp_path):
        """Uses subprocess when no session_key."""
        from abyss.claude_runner import run_claude_with_sdk

        with (
            patch("abyss.sdk_client.is_sdk_available", return_value=True),
            patch("abyss.claude_runner.run_claude", new_callable=AsyncMock) as mock_run,
        ):
            mock_run.return_value = "subprocess response"
            result = await run_claude_with_sdk(
                working_directory=str(tmp_path),
                message="hello",
                session_key=None,
            )

        assert result == "subprocess response"

    @pytest.mark.asyncio
    async def test_run_streaming_with_sdk_pool_success(self, tmp_path):
        """Uses SDK pool streaming when available."""
        from abyss.claude_runner import run_claude_streaming_with_sdk
        from abyss.sdk_client import SDKClientPool, SDKQueryResult

        mock_result = SDKQueryResult(text="streamed", session_id="sess-2")
        mock_pool = MagicMock(spec=SDKClientPool)
        mock_pool.has_session.return_value = False
        mock_pool.query_streaming = AsyncMock(return_value=mock_result)

        with (
            patch("abyss.sdk_client.is_sdk_available", return_value=True),
            patch("abyss.sdk_client.get_pool", return_value=mock_pool),
        ):
            result = await run_claude_streaming_with_sdk(
                working_directory=str(tmp_path),
                message="hello",
                session_key="bot1:chat_1",
            )

        assert result == "streamed"
        mock_pool.query_streaming.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_streaming_with_sdk_fallback(self, tmp_path):
        """Falls back to subprocess streaming when pool fails."""
        from abyss.claude_runner import run_claude_streaming_with_sdk
        from abyss.sdk_client import SDKClientPool

        mock_pool = MagicMock(spec=SDKClientPool)
        mock_pool.has_session.return_value = False
        mock_pool.query_streaming = AsyncMock(side_effect=ConnectionError("pool down"))

        with (
            patch("abyss.sdk_client.is_sdk_available", return_value=True),
            patch("abyss.sdk_client.get_pool", return_value=mock_pool),
            patch(
                "abyss.claude_runner.run_claude_streaming",
                new_callable=AsyncMock,
            ) as mock_stream,
        ):
            mock_stream.return_value = "subprocess streamed"
            result = await run_claude_streaming_with_sdk(
                working_directory=str(tmp_path),
                message="hello",
                session_key="bot1:chat_1",
            )

        assert result == "subprocess streamed"
        mock_stream.assert_called_once()


# --- cancel_sdk_session tests ---


class TestCancelSDKSession:
    @pytest.mark.asyncio
    async def test_cancel_sdk_session_success(self):
        from abyss.claude_runner import cancel_sdk_session
        from abyss.sdk_client import SDKClientPool

        mock_pool = MagicMock(spec=SDKClientPool)
        mock_pool.has_session.return_value = True
        mock_pool.interrupt = AsyncMock(return_value=True)

        with (
            patch("abyss.sdk_client.is_sdk_available", return_value=True),
            patch("abyss.sdk_client.get_pool", return_value=mock_pool),
        ):
            result = await cancel_sdk_session("bot:1")

        assert result is True
        mock_pool.interrupt.assert_called_once_with("bot:1")

    @pytest.mark.asyncio
    async def test_cancel_sdk_session_no_session(self):
        from abyss.claude_runner import cancel_sdk_session
        from abyss.sdk_client import SDKClientPool

        mock_pool = MagicMock(spec=SDKClientPool)
        mock_pool.has_session.return_value = False

        with (
            patch("abyss.sdk_client.is_sdk_available", return_value=True),
            patch("abyss.sdk_client.get_pool", return_value=mock_pool),
        ):
            result = await cancel_sdk_session("bot:999")

        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_sdk_session_sdk_unavailable(self):
        from abyss.claude_runner import cancel_sdk_session

        with patch("abyss.sdk_client.is_sdk_available", return_value=False):
            result = await cancel_sdk_session("bot:1")

        assert result is False
