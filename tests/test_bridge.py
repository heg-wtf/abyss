"""Tests for the Node.js bridge client."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cclaw.bridge import (
    DEFAULT_SOCKET_PATH,
    _bridge_directory,
    _socket_path,
    bridge_close_session,
    bridge_health,
    bridge_query,
    bridge_query_streaming,
    is_bridge_running,
    stop_bridge,
)


class TestBridgeDirectory:
    def test_bridge_directory_installs_files(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CCLAW_HOME", str(tmp_path))
        directory = _bridge_directory()
        assert directory.name == "bridge"
        assert (directory / "package.json").exists()
        assert (directory / "server.mjs").exists()

    def test_bridge_directory_overwrites_server_mjs(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CCLAW_HOME", str(tmp_path))
        # First install
        directory = _bridge_directory()
        old_content = (directory / "server.mjs").read_text()
        # Modify server.mjs
        (directory / "server.mjs").write_text("old version")
        # Re-install should overwrite
        from cclaw.bridge import _install_bridge_files

        _install_bridge_files(directory)
        assert (directory / "server.mjs").read_text() != "old version"

    def test_socket_path_default(self, monkeypatch):
        monkeypatch.delenv("CCLAW_BRIDGE_SOCKET", raising=False)
        assert _socket_path() == DEFAULT_SOCKET_PATH

    def test_socket_path_custom(self, monkeypatch):
        monkeypatch.setenv("CCLAW_BRIDGE_SOCKET", "/custom/path.sock")
        assert _socket_path() == "/custom/path.sock"


class TestBridgeLifecycle:
    def test_is_bridge_running_no_process(self):
        import cclaw.bridge as bridge_module

        bridge_module._bridge_process = None
        assert is_bridge_running() is False

    def test_is_bridge_running_dead_process(self):
        import cclaw.bridge as bridge_module

        mock_process = MagicMock()
        mock_process.poll.return_value = 1  # exited
        bridge_module._bridge_process = mock_process
        assert is_bridge_running() is False
        bridge_module._bridge_process = None

    def test_is_bridge_running_alive_process(self):
        import cclaw.bridge as bridge_module

        mock_process = MagicMock()
        mock_process.poll.return_value = None  # still running
        bridge_module._bridge_process = mock_process
        assert is_bridge_running() is True
        bridge_module._bridge_process = None

    def test_stop_bridge_no_process(self):
        import cclaw.bridge as bridge_module

        bridge_module._bridge_process = None
        stop_bridge()  # should not raise
        assert bridge_module._bridge_process is None

    def test_stop_bridge_terminates_process(self, tmp_path, monkeypatch):
        import cclaw.bridge as bridge_module

        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.wait.return_value = 0
        bridge_module._bridge_process = mock_process

        socket_file = tmp_path / "test.sock"
        socket_file.touch()
        monkeypatch.setenv("CCLAW_BRIDGE_SOCKET", str(socket_file))

        stop_bridge()

        mock_process.terminate.assert_called_once()
        assert bridge_module._bridge_process is None


class TestBridgeProtocol:
    @pytest.fixture
    def mock_connection(self):
        """Create mock reader/writer for Unix socket."""
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        return reader, writer

    @pytest.mark.asyncio
    async def test_bridge_health(self, mock_connection):
        reader, writer = mock_connection
        health_response = (
            json.dumps({"type": "health", "status": "ok", "activeSessions": 2}).encode() + b"\n"
        )
        reader.readline = AsyncMock(return_value=health_response)

        with patch("cclaw.bridge._connect", return_value=(reader, writer)):
            result = await bridge_health()

        assert result["status"] == "ok"
        assert result["activeSessions"] == 2

    @pytest.mark.asyncio
    async def test_bridge_health_connection_error(self):
        with patch("cclaw.bridge._connect", side_effect=ConnectionRefusedError):
            result = await bridge_health()
        assert result is None

    @pytest.mark.asyncio
    async def test_bridge_query(self, mock_connection):
        reader, writer = mock_connection
        response = (
            json.dumps({"type": "result", "text": "Hello!", "sessionId": "uuid-123"}).encode()
            + b"\n"
        )
        reader.readline = AsyncMock(return_value=response)

        with patch("cclaw.bridge._connect", return_value=(reader, writer)):
            result = await bridge_query(
                session_key="bot1:chat_1",
                prompt="hi",
                working_directory="/tmp",
                model="sonnet",
            )

        assert result == "Hello!"

        # Verify the request was sent correctly
        sent_data = writer.write.call_args[0][0]
        request = json.loads(sent_data.decode().strip())
        assert request["action"] == "query"
        assert request["sessionKey"] == "bot1:chat_1"
        assert request["prompt"] == "hi"
        assert request["model"] == "sonnet"

    @pytest.mark.asyncio
    async def test_bridge_query_error_response(self, mock_connection):
        reader, writer = mock_connection
        response = json.dumps({"type": "error", "message": "Session expired"}).encode() + b"\n"
        reader.readline = AsyncMock(return_value=response)

        with patch("cclaw.bridge._connect", return_value=(reader, writer)):
            with pytest.raises(RuntimeError, match="Session expired"):
                await bridge_query(
                    session_key="bot1:chat_1",
                    prompt="hi",
                    working_directory="/tmp",
                )

    @pytest.mark.asyncio
    async def test_bridge_query_connection_error(self):
        with patch("cclaw.bridge._connect", side_effect=FileNotFoundError):
            with pytest.raises(ConnectionError, match="Bridge not reachable"):
                await bridge_query(
                    session_key="bot1:chat_1",
                    prompt="hi",
                    working_directory="/tmp",
                )

    @pytest.mark.asyncio
    async def test_bridge_query_streaming(self, mock_connection):
        reader, writer = mock_connection

        chunks = [
            json.dumps({"type": "text", "text": "Hello "}).encode() + b"\n",
            json.dumps({"type": "text", "text": "world!"}).encode() + b"\n",
            json.dumps({"type": "result", "text": "Hello world!", "sessionId": "uuid-123"}).encode()
            + b"\n",
        ]
        reader.readline = AsyncMock(side_effect=chunks)

        received_chunks = []

        def on_chunk(text):
            received_chunks.append(text)

        with patch("cclaw.bridge._connect", return_value=(reader, writer)):
            result = await bridge_query_streaming(
                session_key="bot1:chat_1",
                prompt="hi",
                working_directory="/tmp",
                on_text_chunk=on_chunk,
            )

        assert result == "Hello world!"
        assert received_chunks == ["Hello ", "world!"]

    @pytest.mark.asyncio
    async def test_bridge_close_session(self):
        # close_session is now a no-op (no persistent session pool)
        await bridge_close_session("bot1:chat_1")  # should not raise


class TestBridgeAwareRunner:
    @pytest.mark.asyncio
    async def test_run_with_bridge_fallback_when_not_running(self, tmp_path):
        """Falls back to subprocess when bridge is not running."""
        from cclaw.claude_runner import run_claude_with_bridge

        with (
            patch("cclaw.bridge.is_bridge_running", return_value=False),
            patch("cclaw.claude_runner.run_claude", new_callable=AsyncMock) as mock_run,
        ):
            mock_run.return_value = "subprocess response"
            result = await run_claude_with_bridge(
                working_directory=str(tmp_path),
                message="hello",
                session_key="bot1:chat_1",
            )

        assert result == "subprocess response"
        mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_with_bridge_success(self, tmp_path):
        """Uses bridge when available."""
        from cclaw.claude_runner import run_claude_with_bridge

        with (
            patch("cclaw.bridge.is_bridge_running", return_value=True),
            patch("cclaw.bridge.bridge_query", new_callable=AsyncMock) as mock_bridge,
        ):
            mock_bridge.return_value = "bridge response"
            result = await run_claude_with_bridge(
                working_directory=str(tmp_path),
                message="hello",
                session_key="bot1:chat_1",
                model="sonnet",
            )

        assert result == "bridge response"
        mock_bridge.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_with_bridge_error_falls_back(self, tmp_path):
        """Falls back to subprocess when bridge returns error."""
        from cclaw.claude_runner import run_claude_with_bridge

        with (
            patch("cclaw.bridge.is_bridge_running", return_value=True),
            patch(
                "cclaw.bridge.bridge_query",
                new_callable=AsyncMock,
                side_effect=ConnectionError("Bridge down"),
            ),
            patch("cclaw.claude_runner.run_claude", new_callable=AsyncMock) as mock_run,
        ):
            mock_run.return_value = "fallback response"
            result = await run_claude_with_bridge(
                working_directory=str(tmp_path),
                message="hello",
                session_key="bot1:chat_1",
            )

        assert result == "fallback response"
        mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_with_bridge_no_session_key_skips_bridge(self, tmp_path):
        """Skips bridge when no session_key (bridge needs it for pooling)."""
        from cclaw.claude_runner import run_claude_with_bridge

        with (
            patch("cclaw.bridge.is_bridge_running", return_value=True),
            patch("cclaw.claude_runner.run_claude", new_callable=AsyncMock) as mock_run,
        ):
            mock_run.return_value = "subprocess response"
            result = await run_claude_with_bridge(
                working_directory=str(tmp_path),
                message="hello",
                session_key=None,
            )

        assert result == "subprocess response"
