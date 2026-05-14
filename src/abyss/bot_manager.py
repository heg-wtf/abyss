"""Bot lifecycle manager for abyss.

Telegram polling is gone — the mobile PWA + dashboard chat are now
the only user-facing surfaces. ``abyss start`` boots:

- The dashboard chat server (in-process aiohttp on 127.0.0.1:3848).
- The abysscope Next.js dashboard as a child subprocess (port 3847).
- Per-bot cron and heartbeat schedulers.
- The QMD HTTP daemon (when available).

The abysscope subprocess used to live behind ``abyss dashboard start``
which was retired in v2026.05.15 in favor of this single lifecycle.
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


async def _run_bots(
    bot_names: list[str] | None = None,
    dashboard_port: int = 3847,
) -> None:
    """Boot the dashboard surface + per-bot schedulers.

    "Running" a bot now means: regenerate its CLAUDE.md, prime the
    FTS5 index, and (if configured) attach cron / heartbeat
    schedulers. The dashboard chat server is started once and serves
    every bot; the abysscope frontend is built and spawned as a child
    subprocess (port ``dashboard_port``).
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

    bot_count = len(bots_to_run)
    prepared_bots: list[tuple[str, dict]] = []

    pid_file = _pid_file()
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()))

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def signal_handler():
        logger.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    cron_tasks: list[asyncio.Task] = []
    heartbeat_tasks: list[asyncio.Task] = []
    chat_server = None
    dashboard_handle = None

    try:
        from abyss import dashboard as dashboard_module
        from abyss.dashboard_ui import (
            BuildProgress,
            BuildStep,
            StepStatus,
            open_build_log,
        )
        from abyss.sdk_client import is_sdk_available

        boot_steps = [
            BuildStep("Prepare bots"),
            BuildStep("SDK availability"),
            BuildStep("QMD daemon"),
            BuildStep("API server"),
            *dashboard_module.build_steps(),
            BuildStep("Cron schedulers"),
            BuildStep("Heartbeat schedulers"),
        ]
        progress = BuildProgress(
            title=f"Booting abyss ({bot_count} bot{'s' if bot_count != 1 else ''})",
            steps=boot_steps,
            console=console,
        )
        log_path = open_build_log(abyss_home())

        with progress.live():
            with progress.step("Prepare bots") as step:
                from abyss.skill import regenerate_bot_claude_md

                ok_names: list[str] = []
                for bot_entry in bots_to_run:
                    name = bot_entry["name"]
                    try:
                        bot_config = load_bot_config(name)
                        if not bot_config:
                            logger.warning("Skipping %s: bot.yaml not found", name)
                            continue
                        regenerate_bot_claude_md(name)
                        bot_path = bot_directory(name)
                        _ensure_conversation_index(name, bot_path)
                        prepared_bots.append((name, bot_config))
                        ok_names.append(name)
                        logger.info("Prepared bot: %s", name)
                    except Exception as bot_error:
                        logger.error("Failed to prepare bot %s: %s", name, bot_error)
                if not prepared_bots:
                    step.status = StepStatus.FAILED
                    step.detail = "no valid bots"
                    raise RuntimeError("No valid bots to start")
                step.detail = ", ".join(ok_names)

            with progress.step("SDK availability") as step:
                if is_sdk_available():
                    step.detail = "Python Agent SDK"
                else:
                    step.status = StepStatus.SKIPPED
                    step.detail = "subprocess fallback"

            with progress.step("QMD daemon") as step:
                if not shutil.which("qmd"):
                    step.status = StepStatus.SKIPPED
                    step.detail = "qmd not installed"
                else:
                    qmd_started = await _start_qmd_daemon()
                    if qmd_started:
                        _ensure_qmd_conversations_collection()
                        step.detail = f"port {QMD_DEFAULT_PORT}"
                    else:
                        step.status = StepStatus.FAILED
                        step.detail = "failed to start"

            with progress.step("API server") as step:
                from abyss.chat_server import get_server as _get_chat_server

                chat_server = _get_chat_server()
                try:
                    await chat_server.start()
                    step.detail = f"http://{chat_server.host}:{chat_server.port}"
                except OSError as chat_error:
                    step.status = StepStatus.FAILED
                    step.detail = f"bind failed: {chat_error}"
                    chat_server = None

            import importlib.metadata

            if dashboard_module.is_port_in_use(dashboard_port):
                # Skip all four dashboard steps cleanly.
                for step_name in (
                    "Locate dashboard",
                    "Install dependencies",
                    "Build dashboard",
                    "Start dashboard server",
                ):
                    target = progress.get(step_name)
                    target.status = StepStatus.SKIPPED
                    target.detail = f"port {dashboard_port} in use"
                progress.refresh()
            else:
                try:
                    abyss_version = importlib.metadata.version("abyss")
                    dashboard_handle = await loop.run_in_executor(
                        None,
                        dashboard_module.build_and_start,
                        dashboard_port,
                        log_path,
                        progress,
                        abyss_version,
                    )
                except (FileNotFoundError, RuntimeError) as dashboard_error:
                    logger.error("Dashboard failed to start: %s", dashboard_error)
                    dashboard_handle = None

            with progress.step("Cron schedulers") as step:
                from abyss.cron import list_cron_jobs, run_cron_scheduler

                attached = 0
                total_jobs = 0
                for name, bot_config in prepared_bots:
                    jobs = list_cron_jobs(name)
                    if jobs:
                        task = asyncio.create_task(run_cron_scheduler(name, bot_config, stop_event))
                        cron_tasks.append(task)
                        attached += 1
                        total_jobs += len(jobs)
                if attached == 0:
                    step.status = StepStatus.SKIPPED
                    step.detail = "no cron jobs"
                else:
                    step.detail = f"{attached} bot(s), {total_jobs} job(s)"

            with progress.step("Heartbeat schedulers") as step:
                from abyss.heartbeat import run_heartbeat_scheduler

                attached = 0
                for name, bot_config in prepared_bots:
                    heartbeat_config = bot_config.get("heartbeat", {})
                    if heartbeat_config.get("enabled"):
                        task = asyncio.create_task(
                            run_heartbeat_scheduler(name, bot_config, stop_event)
                        )
                        heartbeat_tasks.append(task)
                        attached += 1
                if attached == 0:
                    step.status = StepStatus.SKIPPED
                    step.detail = "none enabled"
                else:
                    step.detail = f"{attached} bot(s)"

        if chat_server is not None:
            console.print(
                f"\n[bold green]abyss is up[/bold green] — "
                f"API http://{chat_server.host}:{chat_server.port}",
                end="",
            )
            if dashboard_handle is not None:
                console.print(
                    f" · Dashboard http://localhost:{dashboard_handle.port}",
                    end="",
                )
            console.print()
        console.print("[dim]Press Ctrl+C to stop.[/dim]")
        await stop_event.wait()

    finally:
        console.print("\nStopping bots...")

        if dashboard_handle is not None:
            from abyss import dashboard as dashboard_module

            with suppress(Exception):
                dashboard_module.stop_handle(dashboard_handle)
            console.print("  [dim]Dashboard stopped.[/dim]")

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


def start_bots(
    bot_name: str | None = None,
    foreground: bool = False,
    dashboard_port: int = 3847,
) -> None:
    """Start bot(s) — daemon by default, foreground via ``foreground=True``.

    When ``foreground`` is ``False`` (the default), abyss registers a
    launchd job that re-invokes ``abyss start --foreground`` in the
    background. When ``foreground`` is ``True``, the asyncio loop runs
    directly in the current process — used both for manual debugging
    and as the actual workload launchd ends up executing.
    """
    if not foreground:
        _start_daemon(dashboard_port=dashboard_port)
        return

    bot_names = [bot_name] if bot_name else None

    try:
        asyncio.run(_run_bots(bot_names, dashboard_port=dashboard_port))
    except KeyboardInterrupt:
        pass


def _start_daemon(dashboard_port: int = 3847) -> None:
    """Start abyss as a launchd daemon.

    The launchd job runs ``abyss start --foreground`` so the registered
    job is the actual workload (not another daemon registration).
    """
    plist_path = _plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    venv_bin = Path(sys.executable).parent
    abyss_executable = venv_bin / "abyss"
    extra_args = ["--foreground", "--port", str(dashboard_port)]
    if not abyss_executable.exists():
        abyss_executable = Path(sys.executable)
        abyss_arguments = [str(abyss_executable), "-m", "abyss.cli", "start", *extra_args]
    else:
        abyss_arguments = [str(abyss_executable), "start", *extra_args]

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
    """Stop the running daemon or foreground process + the dashboard."""
    from abyss import dashboard as dashboard_module

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
    sent_signal = False
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            console.print(f"[green]Sent SIGTERM to process {pid}.[/green]")
            sent_signal = True
        except (ValueError, ProcessLookupError):
            pass
        pid_file.unlink(missing_ok=True)

    # Always clean up the dashboard subprocess too — launchd doesn't
    # know about it. The bot_manager normally tears it down on shutdown
    # but a crashed manager or external `kill` can orphan the child.
    dashboard_pid = dashboard_module.stop_running()
    if dashboard_pid is not None:
        console.print(f"[green]Dashboard stopped (PID {dashboard_pid}).[/green]")

    if not sent_signal and not plist_path.exists() and dashboard_pid is None:
        console.print("[yellow]No running abyss process found.[/yellow]")

    _stop_qmd_daemon()


def _show_dashboard_status() -> None:
    """Show Abysscope dashboard status if running."""
    from abyss import dashboard as dashboard_module

    running, pid = dashboard_module.is_running()
    if not running:
        console.print("[dim]Dashboard: not running[/dim]")
        return

    port = dashboard_module.get_port() or dashboard_module.DEFAULT_PORT
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
