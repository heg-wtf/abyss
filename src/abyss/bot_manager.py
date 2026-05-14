"""Bot lifecycle manager for abyss.

Telegram polling is gone — the mobile PWA + dashboard chat are now
the only user-facing surfaces. ``abyss start`` boots the dashboard
chat server (HTTP/SSE on 127.0.0.1:3848), the per-bot cron and
heartbeat schedulers, and the QMD HTTP daemon (when available). No
``Application``, no ``run_polling``, no Telegram token. Conversation
markdown files + the FTS5 index continue to live under each bot's
session directory.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import signal
import subprocess
import sys
from contextlib import suppress
from pathlib import Path

from rich.console import Console

from abyss.config import abyss_home, bot_directory, load_bot_config, load_config
from abyss.utils import setup_logging

logger = logging.getLogger(__name__)
console = Console()

LAUNCHD_LABEL = "com.abyss.daemon"
PID_FILE_NAME = "abyss.pid"


def _pid_file() -> Path:
    """Return path to PID file."""
    return abyss_home() / PID_FILE_NAME


def _plist_path() -> Path:
    """Return path to launchd plist file."""
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"


async def _run_bots(bot_names: list[str] | None = None) -> None:
    """Boot the dashboard surface + per-bot schedulers.

    "Running" a bot now means: regenerate its CLAUDE.md, prime the
    FTS5 index, and (if configured) attach cron / heartbeat
    schedulers. The dashboard chat server is started once and serves
    every bot.
    """
    config = load_config()
    if not config or not config.get("bots"):
        console.print("[red]No bots configured. Run 'abyss init' first.[/red]")
        return

    settings = config.get("settings", {})
    log_level = settings.get("log_level", "INFO")
    setup_logging(log_level)

    from abyss.config import get_claude_code_env

    claude_code_env = get_claude_code_env()
    logger.info(
        "Claude Code env injection enabled: %s",
        ", ".join(sorted(claude_code_env.keys())),
    )

    bots_to_run = config["bots"]
    if bot_names:
        bots_to_run = [b for b in bots_to_run if b["name"] in bot_names]
        if not bots_to_run:
            console.print("[red]No matching bots found.[/red]")
            return

    prepared_bots: list[tuple[str, dict]] = []

    for bot_entry in bots_to_run:
        name = bot_entry["name"]
        try:
            bot_config = load_bot_config(name)
            if not bot_config:
                console.print(f"[yellow]Skipping {name}: bot.yaml not found.[/yellow]")
                continue

            from abyss.skill import regenerate_bot_claude_md

            regenerate_bot_claude_md(name)

            bot_path = bot_directory(name)
            _ensure_conversation_index(name, bot_path)
            prepared_bots.append((name, bot_config))
            logger.info("Prepared bot: %s", name)
        except Exception as error:
            console.print(f"[red]Error preparing {name}: {error}[/red]")
            logger.error("Failed to prepare bot %s: %s", name, error)

    if not prepared_bots:
        console.print("[red]No valid bots to start.[/red]")
        return

    from abyss.sdk_client import is_sdk_available

    if is_sdk_available():
        console.print("  [green]SDK[/green] Python Agent SDK (session continuity)")
    else:
        console.print("  [yellow]SDK[/yellow] Not available, using subprocess fallback")

    if shutil.which("qmd"):
        qmd_started = await _start_qmd_daemon()
        if qmd_started:
            console.print("  [green]QMD[/green] HTTP daemon (port 8181)")
            _ensure_qmd_conversations_collection()
        else:
            console.print("  [yellow]QMD[/yellow] Daemon failed to start")

    console.print(f"Starting {len(prepared_bots)} bot(s)...")
    for name, _ in prepared_bots:
        console.print(f"  [green]OK[/green] {name}")

    pid_file = _pid_file()
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()))

    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()

    def signal_handler():
        logger.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    cron_tasks: list[asyncio.Task] = []
    heartbeat_tasks: list[asyncio.Task] = []
    chat_server = None
    try:
        from abyss.cron import list_cron_jobs, run_cron_scheduler

        for name, bot_config in prepared_bots:
            jobs = list_cron_jobs(name)
            if jobs:
                task = asyncio.create_task(run_cron_scheduler(name, bot_config, stop_event))
                cron_tasks.append(task)
                console.print(f"  [green]CRON[/green] {name} ({len(jobs)} job(s))")

        from abyss.heartbeat import run_heartbeat_scheduler

        for name, bot_config in prepared_bots:
            heartbeat_config = bot_config.get("heartbeat", {})
            if heartbeat_config.get("enabled"):
                task = asyncio.create_task(run_heartbeat_scheduler(name, bot_config, stop_event))
                heartbeat_tasks.append(task)
                interval = heartbeat_config.get("interval_minutes", 30)
                console.print(f"  [green]HEARTBEAT[/green] {name} (every {interval}m)")

        from abyss.chat_server import get_server as _get_chat_server

        chat_server = _get_chat_server()
        try:
            await chat_server.start()
            console.print(
                f"  [green]CHAT[/green] dashboard server "
                f"(http://{chat_server.host}:{chat_server.port})"
            )
        except OSError as chat_error:
            console.print(f"  [yellow]CHAT[/yellow] failed to bind: {chat_error}")
            chat_server = None

        console.print(f"\n{len(prepared_bots)} bot(s) running. Press Ctrl+C to stop.")
        await stop_event.wait()

    finally:
        console.print("\nStopping bots...")

        if chat_server is not None:
            with suppress(Exception):
                await chat_server.stop()

        from abyss.llm import close_all as close_all_backends
        from abyss.sdk_client import close_pool

        await close_all_backends()
        await close_pool()

        from abyss.claude_runner import cancel_all_processes

        killed = cancel_all_processes()
        if killed:
            console.print(f"  Killed {killed} running Claude process(es).")

        for task in cron_tasks:
            task.cancel()
        if cron_tasks:
            await asyncio.gather(*cron_tasks, return_exceptions=True)

        for task in heartbeat_tasks:
            task.cancel()
        if heartbeat_tasks:
            await asyncio.gather(*heartbeat_tasks, return_exceptions=True)

        _stop_qmd_daemon()

        if pid_file.exists():
            pid_file.unlink()

        console.print("[green]All bots stopped.[/green]")


QMD_DEFAULT_PORT = 8181


def _ensure_conversation_index(bot_name: str, bot_path: Path) -> None:
    """Initialize the FTS5 conversation index for a bot.

    The group surface was removed alongside Telegram, so this only
    primes the per-bot db now. Idempotent — safe to call on every
    bot start.
    """
    from abyss import conversation_index

    if not conversation_index.is_fts5_available():
        logger.warning("SQLite FTS5 not available; conversation_search index disabled")
        return

    bot_db = bot_path / "conversation.db"
    conversation_index.ensure_schema(bot_db)


def _ensure_qmd_conversations_collection() -> None:
    """Register abyss conversation logs as a QMD collection if not already done."""
    bots_path = abyss_home() / "bots"
    if not bots_path.exists():
        return

    result = subprocess.run(
        [
            "qmd",
            "collection",
            "add",
            str(bots_path),
            "--name",
            "abyss-conversations",
            "--mask",
            "**/conversation-*.md",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        logger.info("QMD collection 'abyss-conversations' registered")


async def _start_qmd_daemon() -> bool:
    """Start the QMD HTTP MCP daemon if not already running."""
    import shutil

    if not shutil.which("qmd"):
        logger.warning("QMD CLI not found, skipping daemon start")
        return False

    if await _qmd_health_check():
        logger.info("QMD daemon already running")
        return True

    result = subprocess.run(
        ["qmd", "mcp", "--http", "--daemon"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        logger.error("QMD daemon start failed: %s", result.stderr)
        return False

    for _ in range(30):
        if await _qmd_health_check():
            logger.info("QMD daemon started on port %d", QMD_DEFAULT_PORT)
            return True
        await asyncio.sleep(1)

    logger.error("QMD daemon did not become ready within 30s")
    return False


async def _qmd_health_check() -> bool:
    """Check if QMD HTTP daemon is reachable."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("localhost", QMD_DEFAULT_PORT),
            timeout=2,
        )
        writer.close()
        await writer.wait_closed()
        return True
    except (ConnectionRefusedError, asyncio.TimeoutError, OSError):
        return False


def _stop_qmd_daemon() -> None:
    """Stop the QMD HTTP MCP daemon."""
    import shutil

    if not shutil.which("qmd"):
        return

    result = subprocess.run(
        ["qmd", "mcp", "stop"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        logger.info("QMD daemon stopped")


def start_bots(bot_name: str | None = None, daemon: bool = False) -> None:
    """Start bot(s), optionally as a daemon."""
    if daemon:
        _start_daemon()
        return

    bot_names = [bot_name] if bot_name else None

    try:
        asyncio.run(_run_bots(bot_names))
    except KeyboardInterrupt:
        pass


def _start_daemon() -> None:
    """Start abyss as a launchd daemon."""
    plist_path = _plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    venv_bin = Path(sys.executable).parent
    abyss_executable = venv_bin / "abyss"
    if not abyss_executable.exists():
        abyss_executable = Path(sys.executable)
        abyss_arguments = [str(abyss_executable), "-m", "abyss.cli", "start"]
    else:
        abyss_arguments = [str(abyss_executable), "start"]

    log_directory = abyss_home() / "logs"
    log_directory.mkdir(parents=True, exist_ok=True)

    current_path = os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")

    newline = "\n"
    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCHD_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        {newline.join(f"        <string>{arg}</string>" for arg in abyss_arguments)}
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>{current_path}</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_directory / "daemon-stdout.log"}</string>
    <key>StandardErrorPath</key>
    <string>{log_directory / "daemon-stderr.log"}</string>
</dict>
</plist>
"""

    plist_path.write_text(plist_content)

    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    result = subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True, text=True)

    if result.returncode == 0:
        console.print("[green]Daemon started.[/green]")
        console.print(f"  Plist: {plist_path}")
        console.print(f"  Logs:  {log_directory}")
        console.print("\n  Stop with: abyss stop")
    else:
        console.print(f"[red]Failed to start daemon: {result.stderr}[/red]")


def stop_bots() -> None:
    """Stop the running daemon or foreground process."""
    plist_path = _plist_path()

    if plist_path.exists():
        result = subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            capture_output=True,
            text=True,
        )
        plist_path.unlink(missing_ok=True)
        if result.returncode == 0:
            console.print("[green]Daemon stopped.[/green]")
        else:
            console.print(f"[yellow]launchctl unload: {result.stderr.strip()}[/yellow]")

    pid_file = _pid_file()
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            console.print(f"[green]Sent SIGTERM to process {pid}.[/green]")
        except (ValueError, ProcessLookupError):
            pass
        pid_file.unlink(missing_ok=True)
    elif not plist_path.exists():
        console.print("[yellow]No running abyss process found.[/yellow]")

    _stop_qmd_daemon()


def _is_port_in_use(port: int) -> bool:
    """Check if a port is in use."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        return connection.connect_ex(("localhost", port)) == 0


def _show_dashboard_status() -> None:
    """Show Abysscope dashboard status if running."""
    default_port = 3847
    dashboard_pid_file = abyss_home() / "abysscope.pid"
    pid = None
    port = default_port

    if dashboard_pid_file.exists():
        try:
            lines = dashboard_pid_file.read_text().strip().splitlines()
            pid = int(lines[0])
            os.kill(pid, 0)
            port = int(lines[1]) if len(lines) > 1 else default_port
        except (
            ValueError,
            ProcessLookupError,
            PermissionError,
            IndexError,
            OverflowError,
        ):
            pid = None

    if pid is None and not _is_port_in_use(default_port):
        console.print("[dim]Dashboard: not running[/dim]")
        return

    local_ip = _get_local_ip()
    if pid:
        console.print(f"[green]Dashboard: running (PID {pid})[/green]")
    else:
        console.print("[green]Dashboard: running[/green]")
    console.print(f"  Local: http://localhost:{port}")
    console.print(f"  Network: http://{local_ip}:{port}")


def _get_local_ip() -> str:
    """Get local network IP address."""
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.connect(("8.8.8.8", 80))
            return connection.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def show_status() -> None:
    """Show the running status of abyss."""
    from rich.table import Table

    config = load_config()

    pid_file = _pid_file()
    plist_path = _plist_path()

    if plist_path.exists():
        console.print("[green]Daemon: running (launchd)[/green]")
    elif pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            console.print(f"[green]Process: running (PID {pid})[/green]")
        except (ValueError, ProcessLookupError):
            console.print("[yellow]Process: stale PID file[/yellow]")
            pid_file.unlink(missing_ok=True)
    else:
        console.print("[yellow]Status: not running[/yellow]")

    _show_dashboard_status()

    if not config or not config.get("bots"):
        console.print("[yellow]No bots configured.[/yellow]")
        return

    table = Table(title="Bot Status")
    table.add_column("Name", style="cyan")
    table.add_column("Display Name", style="green")
    table.add_column("Sessions", justify="right")

    for bot_entry in config["bots"]:
        name = bot_entry["name"]
        bot_config = load_bot_config(name) or {}
        display_name = bot_config.get("display_name") or name

        session_directory = bot_directory(name) / "sessions"
        session_count = 0
        if session_directory.exists():
            session_count = len([d for d in session_directory.iterdir() if d.is_dir()])

        table.add_row(name, display_name, str(session_count))

    console.print(table)
