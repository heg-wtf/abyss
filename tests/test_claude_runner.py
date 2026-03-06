"""Tests for cclaw.claude_runner module."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cclaw.claude_runner import (
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

MOCK_SUBPROCESS = "cclaw.claude_runner.asyncio.create_subprocess_exec"
MOCK_WHICH = "cclaw.claude_runner.shutil.which"


@pytest.fixture(autouse=True)
def mock_claude_path():
    """Mock shutil.which to always return a claude path and reset cache."""
    import cclaw.claude_runner as runner_module

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
            "cclaw.claude_runner.asyncio.wait_for",
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
    import cclaw.claude_runner as runner_module

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
            "cclaw.skill.merge_mcp_configs",
            return_value=mcp_config,
        ),
        patch(
            "cclaw.skill.collect_skill_environment_variables",
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
        patch("cclaw.skill.merge_mcp_configs", return_value=None),
        patch(
            "cclaw.skill.collect_skill_environment_variables",
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
        patch("cclaw.skill.merge_mcp_configs", return_value=None),
        patch("cclaw.skill.collect_skill_environment_variables", return_value={}),
        patch(
            "cclaw.skill.collect_skill_allowed_tools",
            return_value=["Bash(imsg:*)", "Read(*)"],
        ),
    ):
        mock_exec.return_value = mock_process
        await run_claude(str(tmp_path), "Hello", skill_names=["imessage"])

    call_args = mock_exec.call_args[0]
    assert "--allowedTools" in call_args
    allowed_index = list(call_args).index("--allowedTools")
    assert call_args[allowed_index + 1] == "Bash(imsg:*),Read(*)"

    # Verify .claude/settings.json was created
    settings_path = tmp_path / ".claude" / "settings.json"
    assert settings_path.exists()
    with open(settings_path) as file:
        settings = json.load(file)
    assert "Bash(imsg:*)" in settings["permissions"]["allow"]
    assert "Read(*)" in settings["permissions"]["allow"]


def test_write_session_settings_creates_file(tmp_path):
    """_write_session_settings creates .claude/settings.json with permissions."""
    _write_session_settings(str(tmp_path), ["Bash(reminders:*)", "Bash(osascript:*)"])

    settings_path = tmp_path / ".claude" / "settings.json"
    assert settings_path.exists()
    with open(settings_path) as file:
        settings = json.load(file)
    assert "Bash(reminders:*)" in settings["permissions"]["allow"]
    assert "Bash(osascript:*)" in settings["permissions"]["allow"]


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


def test_write_session_settings_empty_tools(tmp_path):
    """_write_session_settings does nothing with empty tools list."""
    _write_session_settings(str(tmp_path), [])
    assert not (tmp_path / ".claude" / "settings.json").exists()


@pytest.mark.asyncio
async def test_run_claude_without_skill_names():
    """run_claude does not inject MCP/env when skill_names is None."""
    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"output", b""))
    mock_process.returncode = 0

    with patch(MOCK_SUBPROCESS, new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        await run_claude("/tmp/test", "Hello", skill_names=None)

    call_kwargs = mock_exec.call_args[1]
    assert call_kwargs["env"] is None


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
            "cclaw.claude_runner._prepare_skill_config",
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
