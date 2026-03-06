"""Node.js bridge client for Claude Code SDK.

Communicates with bridge/server.mjs via Unix socket using JSONL protocol.
The bridge runs Claude Code queries via the SDK's v1 query() function,
reusing a long-lived Node.js process instead of spawning `claude -p` each time.

Manages bridge process lifecycle (start/stop/health check).
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)

DEFAULT_SOCKET_PATH = "/tmp/cclaw-bridge.sock"
DEFAULT_LOG_PATH = "/tmp/cclaw-bridge.log"
BRIDGE_STARTUP_TIMEOUT_SECONDS = 30

_bridge_process: subprocess.Popen | None = None


def _bridge_directory() -> Path:
    """Return the path to the bridge directory at ~/.cclaw/bridge/.

    If the directory doesn't exist yet, copies the bundled bridge files
    from the package data into ~/.cclaw/bridge/.
    """
    from cclaw.config import cclaw_home

    target = cclaw_home() / "bridge"
    if not (target / "server.mjs").exists():
        _install_bridge_files(target)
    return target


def _install_bridge_files(target: Path) -> None:
    """Copy bundled bridge files (server.mjs, package.json) to target.

    Always overwrites server.mjs to ensure the latest version is used.
    """
    import importlib.resources

    target.mkdir(parents=True, exist_ok=True)

    bridge_package = importlib.resources.files("cclaw") / "bridge_data"
    for filename in ("server.mjs", "package.json"):
        source = bridge_package / filename
        destination = target / filename
        # Always overwrite server.mjs to pick up fixes
        destination.write_text(source.read_text(encoding="utf-8"))
    logger.info("Installed bridge files to %s", target)


def _socket_path() -> str:
    """Return the Unix socket path for the bridge."""
    import os

    return os.environ.get("CCLAW_BRIDGE_SOCKET", DEFAULT_SOCKET_PATH)


def _bridge_log_path() -> str:
    """Return the bridge log file path."""
    import os

    return os.environ.get("CCLAW_BRIDGE_LOG", DEFAULT_LOG_PATH)


def _drain_pipe(pipe, label: str) -> None:
    """Drain a subprocess pipe in a background thread to prevent buffer overflow."""
    try:
        for line in pipe:
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                logger.debug("[bridge:%s] %s", label, text)
    except Exception:
        pass


async def start_bridge() -> bool:
    """Start the Node.js bridge process.

    Returns True if the bridge started successfully, False otherwise.
    """
    global _bridge_process

    if is_bridge_running():
        logger.info("Bridge already running")
        return True

    bridge_directory = _bridge_directory()
    package_json = bridge_directory / "package.json"

    if not package_json.exists():
        logger.error("Bridge package.json not found at %s", package_json)
        return False

    # Ensure dependencies are installed
    node_modules = bridge_directory / "node_modules"
    if not node_modules.exists():
        logger.info("Installing bridge dependencies...")
        install_result = subprocess.run(
            ["npm", "install", "--silent"],
            cwd=bridge_directory,
            capture_output=True,
            text=True,
        )
        if install_result.returncode != 0:
            logger.error("Bridge npm install failed: %s", install_result.stderr)
            return False

    # Start the bridge process
    socket = _socket_path()
    log_path = _bridge_log_path()
    server_path = bridge_directory / "server.mjs"

    logger.info("Starting bridge at %s (log: %s) ...", socket, log_path)

    import os

    _bridge_process = subprocess.Popen(
        ["node", str(server_path)],
        cwd=bridge_directory,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={
            **os.environ,
            "CCLAW_BRIDGE_SOCKET": socket,
            "CCLAW_BRIDGE_LOG": log_path,
        },
    )

    # Wait for BRIDGE_READY signal
    try:
        ready = await _wait_for_bridge_ready(timeout=BRIDGE_STARTUP_TIMEOUT_SECONDS)
        if ready:
            logger.info("Bridge started (pid=%d, log=%s)", _bridge_process.pid, log_path)
            # Start background threads to drain stdout/stderr so pipes don't fill up
            threading.Thread(
                target=_drain_pipe,
                args=(_bridge_process.stdout, "stdout"),
                daemon=True,
            ).start()
            threading.Thread(
                target=_drain_pipe,
                args=(_bridge_process.stderr, "stderr"),
                daemon=True,
            ).start()
            return True
        else:
            logger.error("Bridge did not become ready within %ds", BRIDGE_STARTUP_TIMEOUT_SECONDS)
            stop_bridge()
            return False
    except Exception as error:
        logger.error("Bridge startup error: %s", error)
        stop_bridge()
        return False


async def _wait_for_bridge_ready(timeout: float) -> bool:
    """Wait for the bridge to emit BRIDGE_READY on stdout."""
    if not _bridge_process or not _bridge_process.stdout:
        return False

    loop = asyncio.get_event_loop()
    start_time = time.monotonic()

    while time.monotonic() - start_time < timeout:
        # Check if process died
        if _bridge_process.poll() is not None:
            stderr = _bridge_process.stderr.read().decode() if _bridge_process.stderr else ""
            logger.error("Bridge process died during startup: %s", stderr[:500])
            return False

        # Try to read a line (non-blocking)
        try:
            line = await asyncio.wait_for(
                loop.run_in_executor(None, _bridge_process.stdout.readline),
                timeout=1.0,
            )
            if line and b"BRIDGE_READY" in line:
                return True
        except asyncio.TimeoutError:
            continue

    return False


def stop_bridge() -> None:
    """Stop the bridge process."""
    global _bridge_process

    if _bridge_process is None:
        return

    if _bridge_process.poll() is None:
        _bridge_process.terminate()
        try:
            _bridge_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _bridge_process.kill()
            _bridge_process.wait()
        logger.info("Bridge stopped")

    _bridge_process = None

    # Clean up socket file
    socket = Path(_socket_path())
    if socket.exists():
        socket.unlink()


def is_bridge_running() -> bool:
    """Check if the bridge process is alive."""
    return _bridge_process is not None and _bridge_process.poll() is None


async def bridge_health() -> dict[str, Any] | None:
    """Check bridge health. Returns health info or None if unavailable."""
    try:
        response = await _send_request({"action": "health"})
        return response
    except Exception:
        return None


async def _connect() -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Connect to the bridge Unix socket."""
    socket = _socket_path()
    return await asyncio.open_unix_connection(socket)


async def _send_request(request: dict[str, Any]) -> dict[str, Any]:
    """Send a single request and return the first response line."""
    reader, writer = await _connect()
    try:
        writer.write(json.dumps(request).encode() + b"\n")
        await writer.drain()

        line = await asyncio.wait_for(reader.readline(), timeout=300)
        if not line:
            raise RuntimeError("Bridge returned empty response")
        return json.loads(line.decode())
    finally:
        writer.close()
        await writer.wait_closed()


async def _send_request_streaming(
    request: dict[str, Any],
) -> AsyncIterator[dict[str, Any]]:
    """Send a request and yield response lines as they arrive."""
    reader, writer = await _connect()
    try:
        writer.write(json.dumps(request).encode() + b"\n")
        await writer.drain()

        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=300)
            if not line:
                break
            data = json.loads(line.decode())
            yield data
            if data.get("type") in ("result", "error", "ok"):
                break
    finally:
        writer.close()
        await writer.wait_closed()


async def bridge_query(
    session_key: str,
    prompt: str,
    working_directory: str,
    model: str | None = None,
    session_id: str | None = None,
    resume_session: bool = False,
    permission_mode: str = "acceptEdits",
    allowed_tools: list[str] | None = None,
    system_prompt: str | None = None,
    mcp_servers: dict | None = None,
    environment_variables: dict[str, str] | None = None,
    timeout: int = 300,
) -> str:
    """Send a query to the bridge and return the response text.

    The bridge runs Claude Code via the SDK's v1 query() function,
    which reads CLAUDE.md from cwd and supports all tools (Bash, etc.).

    Raises:
        RuntimeError: If the bridge returns an error.
        TimeoutError: If the query times out.
        ConnectionError: If the bridge is not reachable.
    """
    request = {
        "action": "query",
        "sessionKey": session_key,
        "prompt": prompt,
        "cwd": working_directory,
        "streaming": False,
    }

    if model:
        request["model"] = model
    if session_id:
        request["sessionId"] = session_id
        request["resume"] = resume_session
    if permission_mode:
        request["permissionMode"] = permission_mode
    if allowed_tools:
        request["allowedTools"] = allowed_tools
    if system_prompt:
        request["systemPrompt"] = system_prompt
    if mcp_servers:
        request["mcpServers"] = mcp_servers
    if environment_variables:
        request["env"] = environment_variables

    try:
        response = await asyncio.wait_for(
            _send_request(request),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        raise TimeoutError(f"Bridge query timed out after {timeout}s")
    except (ConnectionRefusedError, FileNotFoundError) as error:
        raise ConnectionError(f"Bridge not reachable: {error}") from error

    if response.get("type") == "error":
        raise RuntimeError(f"Bridge error: {response.get('message', 'unknown')}")

    return response.get("text", "")


async def bridge_query_streaming(
    session_key: str,
    prompt: str,
    working_directory: str,
    on_text_chunk: Any | None = None,
    model: str | None = None,
    session_id: str | None = None,
    resume_session: bool = False,
    permission_mode: str = "acceptEdits",
    allowed_tools: list[str] | None = None,
    system_prompt: str | None = None,
    mcp_servers: dict | None = None,
    environment_variables: dict[str, str] | None = None,
    timeout: int = 300,
) -> str:
    """Send a streaming query to the bridge.

    Calls on_text_chunk for each text chunk received.
    Returns the final complete text.
    """
    request = {
        "action": "query",
        "sessionKey": session_key,
        "prompt": prompt,
        "cwd": working_directory,
        "streaming": True,
    }

    if model:
        request["model"] = model
    if session_id:
        request["sessionId"] = session_id
        request["resume"] = resume_session
    if permission_mode:
        request["permissionMode"] = permission_mode
    if allowed_tools:
        request["allowedTools"] = allowed_tools
    if system_prompt:
        request["systemPrompt"] = system_prompt
    if mcp_servers:
        request["mcpServers"] = mcp_servers
    if environment_variables:
        request["env"] = environment_variables

    result_text = ""

    try:
        async for data in _send_request_streaming(request):
            if data.get("type") == "text" and on_text_chunk:
                text = data.get("text", "")
                if text:
                    try:
                        callback_result = on_text_chunk(text)
                        if asyncio.iscoroutine(callback_result):
                            await callback_result
                    except Exception as callback_error:
                        logger.debug("Stream chunk callback error: %s", callback_error)

            if data.get("type") == "result":
                result_text = data.get("text", "")

            if data.get("type") == "error":
                raise RuntimeError(f"Bridge error: {data.get('message', 'unknown')}")
    except asyncio.TimeoutError:
        raise TimeoutError(f"Bridge streaming query timed out after {timeout}s")
    except (ConnectionRefusedError, FileNotFoundError) as error:
        raise ConnectionError(f"Bridge not reachable: {error}") from error

    return result_text


async def bridge_close_session(session_key: str) -> None:
    """Close a specific session on the bridge.

    Note: With the simplified bridge (no persistent session pool),
    this is a no-op but kept for API compatibility.
    """
    logger.debug("bridge_close_session called for %s (no-op)", session_key)
