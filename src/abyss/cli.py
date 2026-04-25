"""abyss CLI - Typer application entry point."""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(help="abyss - Telegram + Claude Code AI assistant", invoke_without_command=True)


ASCII_ART = r"""
  ██████╗ ██████╗██╗      █████╗ ██╗    ██╗
 ██╔════╝██╔════╝██║     ██╔══██╗██║    ██║
 ██║     ██║     ██║     ███████║██║ █╗ ██║
 ██║     ██║     ██║     ██╔══██║██║███╗██║
 ╚██████╗╚██████╗███████╗██║  ██║╚███╔███╔╝
  ╚═════╝ ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝
  Telegram + Claude Code AI Assistant
"""


@app.callback()
def main(context: typer.Context) -> None:
    """abyss - Telegram + Claude Code AI assistant."""
    if context.invoked_subcommand is None:
        from rich.console import Console

        from abyss import __version__

        console = Console()
        console.print(f"[cyan]{ASCII_ART}[/cyan]")
        console.print(f"  [dim]v{__version__}[/dim]\n")
        console.print("Run [green]abyss --help[/green] for available commands.\n")


bot_app = typer.Typer(help="Bot management")
app.add_typer(bot_app, name="bot")
skill_app = typer.Typer(help="Skill management", invoke_without_command=True)
app.add_typer(skill_app, name="skills")
cron_app = typer.Typer(help="Cron job management")
app.add_typer(cron_app, name="cron")
memory_app = typer.Typer(help="Bot memory management")
app.add_typer(memory_app, name="memory")
global_memory_app = typer.Typer(help="Global memory management (shared across all bots)")
app.add_typer(global_memory_app, name="global-memory")
heartbeat_app = typer.Typer(help="Heartbeat management")
app.add_typer(heartbeat_app, name="heartbeat")
dashboard_app = typer.Typer(help="Abysscope web dashboard")
app.add_typer(dashboard_app, name="dashboard")
group_app = typer.Typer(help="Group management for multi-bot collaboration")
app.add_typer(group_app, name="group")


@app.command()
def init() -> None:
    """Run initial setup wizard."""
    from abyss.onboarding import run_onboarding

    run_onboarding()


@app.command()
def start(
    bot: str = typer.Option(None, help="Start specific bot only"),
    daemon: bool = typer.Option(False, help="Run as background daemon"),
) -> None:
    """Start bot(s)."""
    from abyss.bot_manager import start_bots

    start_bots(bot_name=bot, daemon=daemon)


@app.command()
def stop() -> None:
    """Stop daemon."""
    from abyss.bot_manager import stop_bots

    stop_bots()


@app.command()
def restart(
    bot: str = typer.Option(None, help="Restart specific bot only"),
    daemon: bool = typer.Option(False, help="Run as background daemon"),
) -> None:
    """Restart bot(s). Stops then starts."""
    from abyss.bot_manager import start_bots, stop_bots

    stop_bots()
    start_bots(bot_name=bot, daemon=daemon)


@app.command()
def status() -> None:
    """Show running status."""
    from abyss.bot_manager import show_status

    show_status()


@app.command()
def doctor() -> None:
    """Check environment and configuration."""
    from abyss.onboarding import run_doctor

    run_doctor()


@app.command()
def reindex(
    bot: str = typer.Option(
        None, "--bot", "-b", help="Rebuild a specific bot's conversation index."
    ),
    group: str = typer.Option(
        None, "--group", "-g", help="Rebuild a specific group's conversation index."
    ),
    all_scopes: bool = typer.Option(
        False, "--all", help="Rebuild every bot and group conversation index."
    ),
) -> None:
    """Rebuild SQLite FTS5 conversation indexes from markdown logs.

    Markdown is the source of truth — this command wipes the affected
    DB and re-inserts every parsed message. Safe to run repeatedly.
    """
    from rich.console import Console

    from abyss import conversation_index
    from abyss.config import bot_directory, load_config
    from abyss.group import group_directory, list_groups

    console = Console()

    if not conversation_index.is_fts5_available():
        console.print("[red]SQLite FTS5 is not available — cannot reindex.[/red]")
        raise typer.Exit(code=1)

    selected_bots: list[str] = []
    selected_groups: list[str] = []

    if bot:
        selected_bots = [bot]
    if group:
        selected_groups = [group]
    if all_scopes:
        config = load_config() or {}
        selected_bots = [entry["name"] for entry in config.get("bots", [])]
        selected_groups = [entry["name"] for entry in list_groups()]

    if not selected_bots and not selected_groups:
        console.print("[yellow]Specify --bot NAME, --group NAME, or --all.[/yellow]")
        raise typer.Exit(code=2)

    total = 0
    for bot_name in selected_bots:
        bot_path = bot_directory(bot_name)
        if not bot_path.exists():
            console.print(f"[yellow]Skip {bot_name}: bot directory missing.[/yellow]")
            continue
        sessions_root = bot_path / "sessions"
        db_path = bot_path / "conversation.db"
        count = conversation_index.reindex_session_dir(db_path, sessions_root)
        console.print(f"[green]bot[/green] {bot_name}: indexed {count} message(s)")
        total += count

    for group_name in selected_groups:
        gdir = group_directory(group_name)
        if not gdir.exists():
            console.print(f"[yellow]Skip group {group_name}: directory missing.[/yellow]")
            continue
        conv_dir = gdir / "conversation"
        db_path = gdir / "conversation.db"
        count = conversation_index.reindex_group_dir(db_path, conv_dir)
        console.print(f"[green]group[/green] {group_name}: indexed {count} message(s)")
        total += count

    console.print(f"[bold]Reindex complete: {total} total messages.[/bold]")


@app.command()
def backup() -> None:
    """Backup ~/.abyss/ to a password-encrypted zip file."""
    import getpass

    from rich.console import Console

    from abyss.backup import create_encrypted_backup, generate_backup_filename
    from abyss.config import abyss_home

    console = Console()
    home = abyss_home()

    if not home.exists():
        console.print(f"[red]abyss home not found: {home}[/red]")
        raise typer.Exit(1)

    filename = generate_backup_filename()
    output_path = Path.cwd() / filename

    if output_path.exists():
        overwrite = typer.confirm(f"{filename} already exists. Overwrite?")
        if not overwrite:
            console.print("[yellow]Backup cancelled.[/yellow]")
            raise typer.Exit()

    password = getpass.getpass("Password: ")
    if not password:
        console.print("[red]Password cannot be empty.[/red]")
        raise typer.Exit(1)

    password_confirm = getpass.getpass("Confirm password: ")
    if password != password_confirm:
        console.print("[red]Passwords do not match.[/red]")
        raise typer.Exit(1)

    with console.status("Creating encrypted backup..."):
        file_count = create_encrypted_backup(output_path, password, home)

    size_megabytes = output_path.stat().st_size / (1024 * 1024)
    console.print("\n[green]Backup complete![/green]")
    console.print(f"  File: {output_path}")
    console.print(f"  Files: {file_count}")
    console.print(f"  Size: {size_megabytes:.1f} MB")
    console.print("  Encryption: AES-256")


DASHBOARD_PID_FILE_NAME = "abysscope.pid"
DASHBOARD_DEFAULT_PORT = 3847


def _dashboard_pid_file() -> Path:
    from abyss.config import abyss_home

    return abyss_home() / DASHBOARD_PID_FILE_NAME


def _find_abysscope_directory() -> Path | None:
    """Find Abysscope directory: cwd → bundled package data → source-relative."""
    candidates = [
        Path.cwd() / "abysscope",
        Path(__file__).resolve().parent / "abysscope_data",
        Path(__file__).resolve().parent.parent.parent / "abysscope",
    ]
    return next((c for c in candidates if c.exists()), None)


def _ensure_node_modules(abysscope_directory: Path) -> None:
    """Install npm dependencies if not present."""
    import subprocess

    from rich.console import Console

    node_modules = abysscope_directory / "node_modules"
    if not node_modules.exists():
        console = Console()
        console.print("[yellow]Installing dependencies...[/yellow]")
        subprocess.run(["npm", "install"], cwd=abysscope_directory, check=True)


def _is_port_in_use(port: int) -> bool:
    """Check if a port is in use."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        return connection.connect_ex(("localhost", port)) == 0


def _is_dashboard_running() -> tuple[bool, int | None]:
    """Check if dashboard is running. Returns (running, pid)."""
    pid_file = _dashboard_pid_file()
    if pid_file.exists():
        try:
            lines = pid_file.read_text().strip().splitlines()
            pid = int(lines[0])
            import os

            os.kill(pid, 0)
            return True, pid
        except (ValueError, ProcessLookupError, PermissionError, IndexError, OverflowError):
            pid_file.unlink(missing_ok=True)

    # Fallback: check if default port is in use
    if _is_port_in_use(DASHBOARD_DEFAULT_PORT):
        return True, None
    return False, None


def _get_dashboard_port() -> int | None:
    """Read port from pid file (second line, if present)."""
    pid_file = _dashboard_pid_file()
    if not pid_file.exists():
        return None
    try:
        lines = pid_file.read_text().strip().splitlines()
        return int(lines[1]) if len(lines) > 1 else DASHBOARD_DEFAULT_PORT
    except (ValueError, IndexError):
        return DASHBOARD_DEFAULT_PORT


@dashboard_app.command("start")
def dashboard_start(
    port: int = typer.Option(DASHBOARD_DEFAULT_PORT, help="Port to run dashboard on"),
    daemon: bool = typer.Option(False, help="Run as background process"),
) -> None:
    """Start Abysscope web dashboard."""
    import os
    import subprocess

    from rich.console import Console

    console = Console()

    running, existing_pid = _is_dashboard_running()
    if running:
        existing_port = _get_dashboard_port()
        message = "[yellow]Abysscope is already running"
        message += f" (PID {existing_pid}, port {existing_port})[/yellow]"
        console.print(message)
        raise typer.Exit(0)

    abysscope_directory = _find_abysscope_directory()
    if abysscope_directory is None:
        console.print("[red]Abysscope directory not found.[/red]")
        console.print("[dim]Run this command from the abyss repo root,[/dim]")
        console.print("[dim]or reinstall abyss to bundle Abysscope.[/dim]")
        raise typer.Exit(1)

    _ensure_node_modules(abysscope_directory)

    if daemon:
        process = subprocess.Popen(
            ["npx", "next", "dev", "--port", str(port)],
            cwd=abysscope_directory,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        pid_file = _dashboard_pid_file()
        pid_file.write_text(f"{process.pid}\n{port}\n")
        console.print(f"[green]Abysscope started on http://localhost:{port}[/green]")
        console.print(f"  PID:  {process.pid}")
        console.print("  Stop: abyss dashboard stop")
    else:
        pid_file = _dashboard_pid_file()
        pid_file.write_text(f"{os.getpid()}\n{port}\n")
        console.print(f"[green]Starting Abysscope on http://localhost:{port}[/green]")
        try:
            subprocess.run(
                ["npx", "next", "dev", "--port", str(port)],
                cwd=abysscope_directory,
                check=True,
            )
        except KeyboardInterrupt:
            console.print("\n[yellow]Dashboard stopped.[/yellow]")
        finally:
            pid_file.unlink(missing_ok=True)


@dashboard_app.command("stop")
def dashboard_stop() -> None:
    """Stop Abysscope web dashboard."""
    import signal

    from rich.console import Console

    console = Console()

    running, pid = _is_dashboard_running()
    if not running:
        console.print("[yellow]Abysscope is not running.[/yellow]")
        _dashboard_pid_file().unlink(missing_ok=True)
        raise typer.Exit(0)

    if pid is None:
        port = _get_dashboard_port() or DASHBOARD_DEFAULT_PORT
        console.print(f"[yellow]Dashboard detected on port {port} but no PID available.[/yellow]")
        console.print("[dim]Stop it manually (e.g. kill the process using the port).[/dim]")
        raise typer.Exit(1)

    try:
        import os

        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

    _dashboard_pid_file().unlink(missing_ok=True)
    console.print(f"[green]Abysscope stopped (PID {pid})[/green]")


@dashboard_app.command("restart")
def dashboard_restart(
    port: int = typer.Option(DASHBOARD_DEFAULT_PORT, help="Port to run dashboard on"),
    daemon: bool = typer.Option(False, help="Run as background process"),
) -> None:
    """Restart Abysscope web dashboard."""
    import time

    running, _ = _is_dashboard_running()
    if running:
        dashboard_stop()
        time.sleep(1)
    dashboard_start(port=port, daemon=daemon)


@dashboard_app.command("status")
def dashboard_status() -> None:
    """Show Abysscope dashboard status."""
    from rich.console import Console

    console = Console()

    running, pid = _is_dashboard_running()
    port = _get_dashboard_port()

    if running:
        display_port = port or DASHBOARD_DEFAULT_PORT
        console.print("[green]Abysscope is running[/green]")
        if pid:
            console.print(f"  PID:  {pid}")
        console.print(f"  Port: {display_port}")
        console.print(f"  URL:  http://localhost:{display_port}")
    else:
        console.print("[yellow]Abysscope is not running.[/yellow]")


@bot_app.command("add")
def bot_add() -> None:
    """Add a new bot."""
    from abyss.onboarding import add_bot

    add_bot()


@bot_app.command("list")
def bot_list() -> None:
    """List all bots."""
    from rich.console import Console
    from rich.table import Table

    from abyss.config import load_config

    console = Console()
    config = load_config()

    if not config or not config.get("bots"):
        console.print("[yellow]No bots configured. Run 'abyss init' or 'abyss bot add'.[/yellow]")
        return

    table = Table(title="Registered Bots")
    table.add_column("Name", style="cyan")
    table.add_column("Model", style="magenta")
    table.add_column("Telegram", style="green")
    table.add_column("Path", style="dim")

    for bot_entry in config["bots"]:
        from abyss.config import DEFAULT_MODEL, bot_directory, load_bot_config

        bot_config = load_bot_config(bot_entry["name"])
        telegram_username = bot_config.get("telegram_username", "N/A") if bot_config else "N/A"
        model = bot_config.get("model", DEFAULT_MODEL) if bot_config else DEFAULT_MODEL
        path = str(bot_directory(bot_entry["name"]))
        table.add_row(bot_entry["name"], model, telegram_username, path)

    console.print(table)


@bot_app.command("remove")
def bot_remove(name: str) -> None:
    """Remove a bot."""
    import shutil

    from rich.console import Console

    from abyss.config import bot_directory as get_bot_directory
    from abyss.config import load_config, save_config

    console = Console()
    config = load_config()

    if not config or not config.get("bots"):
        console.print("[red]No bots configured.[/red]")
        raise typer.Exit(1)

    bot_entry = next((b for b in config["bots"] if b["name"] == name), None)
    if not bot_entry:
        console.print(f"[red]Bot '{name}' not found.[/red]")
        raise typer.Exit(1)

    confirmed = typer.confirm(f"Remove bot '{name}'? This will delete all data.")
    if not confirmed:
        console.print("[yellow]Cancelled.[/yellow]")
        return

    target_directory = get_bot_directory(name)
    if target_directory.exists():
        shutil.rmtree(target_directory)

    config["bots"] = [b for b in config["bots"] if b["name"] != name]
    save_config(config)

    console.print(f"[green]Bot '{name}' removed.[/green]")


@skill_app.callback()
def skills_callback(context: typer.Context) -> None:
    """Skill management."""
    if context.invoked_subcommand is None:
        from rich.console import Console
        from rich.table import Table

        from abyss.builtin_skills import list_builtin_skills
        from abyss.skill import bots_using_skill, list_skills

        console = Console()
        installed_skills = list_skills()
        installed_names = {skill["name"] for skill in installed_skills}

        builtin_skills = list_builtin_skills()
        not_installed_builtins = [
            skill for skill in builtin_skills if skill["name"] not in installed_names
        ]

        if not installed_skills and not not_installed_builtins:
            console.print("[yellow]No skills found. Run 'abyss skills add' to create one.[/yellow]")
            return

        builtin_names = {skill["name"] for skill in builtin_skills}

        table = Table(title="All Skills", expand=False)
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Type", style="magenta", no_wrap=True)
        table.add_column("Status", style="green", no_wrap=True)
        table.add_column("Bots", style="dim", no_wrap=True)

        for skill in installed_skills:
            type_display = "builtin" if skill["name"] in builtin_names else "custom"
            status = skill["status"]
            status_style = "green" if status == "active" else "yellow"
            connected_bots = ", ".join(bots_using_skill(skill["name"])) or "-"
            table.add_row(
                skill["name"],
                type_display,
                f"[{status_style}]{status}[/{status_style}]",
                connected_bots,
            )

        for skill in not_installed_builtins:
            table.add_row(
                skill["name"],
                "builtin",
                "[dim]not installed[/dim]",
                "-",
            )

        console.print(table)

        if not_installed_builtins:
            names = ", ".join(skill["name"] for skill in not_installed_builtins)
            console.print(f"\nInstall built-in skills: [cyan]abyss skills install <{names}>[/cyan]")


logs_app = typer.Typer(help="Log management", invoke_without_command=True)
app.add_typer(logs_app, name="logs")


@logs_app.callback()
def logs_callback(
    context: typer.Context,
    lines: int = typer.Option(50, "--lines", "-n", help="Number of lines to show"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output"),
) -> None:
    """Show today's log file."""
    if context.invoked_subcommand is not None:
        return

    import subprocess
    from datetime import datetime

    from rich.console import Console

    from abyss.config import abyss_home

    console = Console()
    log_directory = abyss_home() / "logs"
    today = datetime.now().strftime("%y%m%d")
    log_file = log_directory / f"abyss-{today}.log"

    if not log_file.exists():
        console.print("[yellow]No log file for today.[/yellow]")
        raise typer.Exit()

    command = ["tail", f"-n{lines}"]
    if follow:
        command.append("-f")
    command.append(str(log_file))

    try:
        subprocess.run(command)
    except KeyboardInterrupt:
        pass


@logs_app.command("clean")
def logs_clean(
    days: int = typer.Option(7, "--days", "-d", help="Keep logs from the last N days"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show files to delete without deleting"),
) -> None:
    """Delete old log files, keeping the last N days (default: 7)."""
    from datetime import datetime, timedelta

    from rich.console import Console

    from abyss.config import abyss_home

    console = Console()
    log_directory = abyss_home() / "logs"

    if not log_directory.exists():
        console.print("[yellow]No logs directory found.[/yellow]")
        return

    log_files = sorted(log_directory.glob("abyss-*.log"))
    if not log_files:
        console.print("[yellow]No log files found.[/yellow]")
        return

    cutoff_date = datetime.now() - timedelta(days=days)
    cutoff_string = cutoff_date.strftime("%y%m%d")

    files_to_delete = []
    for log_file in log_files:
        # Extract YYMMDD from filename: abyss-YYMMDD.log
        date_part = log_file.stem.replace("abyss-", "")
        if date_part < cutoff_string:
            files_to_delete.append(log_file)

    if not files_to_delete:
        console.print(f"[green]No log files older than {days} days. Nothing to clean.[/green]")
        console.print(f"  Total log files: {len(log_files)}")
        return

    if dry_run:
        console.print(f"[cyan]Dry run: would delete {len(files_to_delete)} file(s):[/cyan]")
        for log_file in files_to_delete:
            size = log_file.stat().st_size
            console.print(f"  {log_file.name} ({size:,} bytes)")
        return

    for log_file in files_to_delete:
        log_file.unlink()

    console.print(
        f"[green]Deleted {len(files_to_delete)} log file(s) older than {days} days.[/green]"
    )
    console.print(f"  Remaining: {len(log_files) - len(files_to_delete)} file(s)")


@bot_app.command("model")
def bot_model(
    name: str = typer.Argument(help="Bot name"),
    model: str = typer.Argument(None, help="Model to set (sonnet/opus/haiku)"),
) -> None:
    """Show or change the model for a bot."""
    from rich.console import Console

    from abyss.config import (
        DEFAULT_MODEL,
        VALID_MODELS,
        is_valid_model,
        load_bot_config,
        save_bot_config,
    )

    console = Console()
    bot_config = load_bot_config(name)
    if not bot_config:
        console.print(f"[red]Bot '{name}' not found.[/red]")
        raise typer.Exit(1)

    if model is None:
        current = bot_config.get("model", DEFAULT_MODEL)
        console.print(f"[cyan]{name}[/cyan] model: [magenta]{current}[/magenta]")
        return

    if not is_valid_model(model):
        console.print(f"[red]Invalid model: {model}[/red]")
        console.print(f"Available: {', '.join(VALID_MODELS)}")
        raise typer.Exit(1)

    bot_config["model"] = model
    save_bot_config(name, bot_config)
    console.print(f"[green]{name} model changed to {model}[/green]")


@bot_app.command("streaming")
def bot_streaming(
    name: str = typer.Argument(help="Bot name"),
    value: str = typer.Argument(None, help="on or off"),
) -> None:
    """Show or toggle streaming mode for a bot."""
    from rich.console import Console

    from abyss.config import DEFAULT_STREAMING, load_bot_config, save_bot_config

    console = Console()
    bot_config = load_bot_config(name)
    if not bot_config:
        console.print(f"[red]Bot '{name}' not found.[/red]")
        raise typer.Exit(1)

    if value is None:
        current = bot_config.get("streaming", DEFAULT_STREAMING)
        status_text = "on" if current else "off"
        console.print(f"[cyan]{name}[/cyan] streaming: [magenta]{status_text}[/magenta]")
        return

    if value.lower() == "on":
        bot_config["streaming"] = True
        save_bot_config(name, bot_config)
        console.print(f"[green]{name} streaming enabled[/green]")
    elif value.lower() == "off":
        bot_config["streaming"] = False
        save_bot_config(name, bot_config)
        console.print(f"[green]{name} streaming disabled[/green]")
    else:
        console.print("[red]Invalid value. Use 'on' or 'off'.[/red]")
        raise typer.Exit(1)


@bot_app.command("compact")
def bot_compact(
    name: str = typer.Argument(help="Bot name"),
    model: str = typer.Option("sonnet", help="Model for compaction"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Compact bot's MD files to save tokens."""
    import asyncio

    from rich.console import Console

    from abyss.config import load_bot_config
    from abyss.skill import regenerate_bot_claude_md, update_session_claude_md
    from abyss.token_compact import (
        collect_compact_targets,
        format_compact_report,
        run_compact,
        save_compact_results,
    )

    console = Console()

    bot_config = load_bot_config(name)
    if not bot_config:
        console.print(f"[red]Bot '{name}' not found.[/red]")
        raise typer.Exit(1)

    targets = collect_compact_targets(name)
    if not targets:
        console.print("[yellow]No compactable files found.[/yellow]")
        return

    console.print(f"[cyan]Found {len(targets)} file(s) to compact:[/cyan]")
    for target in targets:
        console.print(
            f"  - {target.label} ({target.line_count} lines, ~{target.token_count:,} tokens)"
        )

    console.print("\n[cyan]Compacting...[/cyan]")

    results = asyncio.run(run_compact(name, model=model))
    report = format_compact_report(name, results)
    console.print(f"\n{report}")

    successful = [r for r in results if r.error is None]
    if not successful:
        console.print("[yellow]No files were successfully compacted.[/yellow]")
        return

    if not yes:
        confirmed = typer.confirm("Save compacted files?")
        if not confirmed:
            console.print("[yellow]Cancelled.[/yellow]")
            return

    save_compact_results(results)
    from abyss.config import bot_directory

    regenerate_bot_claude_md(name)
    update_session_claude_md(bot_directory(name))
    console.print("[green]Compacted files saved. CLAUDE.md regenerated.[/green]")


@bot_app.command("edit")
def bot_edit(name: str) -> None:
    """Edit bot configuration."""
    import subprocess

    from rich.console import Console

    from abyss.config import bot_directory, load_bot_config

    console = Console()
    bot_config = load_bot_config(name)

    if not bot_config:
        console.print(f"[red]Bot '{name}' not found.[/red]")
        raise typer.Exit(1)

    bot_yaml_path = bot_directory(name) / "bot.yaml"
    editor = "vi"
    subprocess.run([editor, str(bot_yaml_path)])


@skill_app.command("builtins")
def skill_builtins() -> None:
    """List available built-in skills."""
    from rich.console import Console
    from rich.table import Table

    from abyss.builtin_skills import list_builtin_skills
    from abyss.skill import is_skill

    console = Console()
    builtin_skills = list_builtin_skills()

    if not builtin_skills:
        console.print("[yellow]No built-in skills available.[/yellow]")
        return

    table = Table(title="Built-in Skills", expand=False)
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Description", style="dim")
    table.add_column("Installed", style="green", no_wrap=True)

    for skill in builtin_skills:
        installed = is_skill(skill["name"])
        installed_display = "[green]yes[/green]" if installed else "[dim]no[/dim]"
        table.add_row(skill["name"], skill["description"], installed_display)

    console.print(table)
    console.print("\nInstall with: [cyan]abyss skills install <name>[/cyan]")


@skill_app.command("install")
def skill_install(
    name: str = typer.Argument(None, help="Built-in skill name to install"),
) -> None:
    """Install a built-in skill (or list available ones)."""
    from rich.console import Console
    from rich.table import Table

    from abyss.builtin_skills import list_builtin_skills
    from abyss.skill import (
        activate_skill,
        check_skill_requirements,
        install_builtin_skill,
        is_skill,
    )

    console = Console()

    if name is None:
        builtin_skills = list_builtin_skills()
        if not builtin_skills:
            console.print("[yellow]No built-in skills available.[/yellow]")
            return

        table = Table(title="Built-in Skills", expand=False)
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Description", style="dim")
        table.add_column("Installed", style="green", no_wrap=True)

        for skill in builtin_skills:
            installed = is_skill(skill["name"])
            installed_display = "[green]yes[/green]" if installed else "[dim]no[/dim]"
            table.add_row(skill["name"], skill["description"], installed_display)

        console.print(table)
        console.print("\nInstall with: [cyan]abyss skills install <name>[/cyan]")
        return

    try:
        directory = install_builtin_skill(name)
    except ValueError:
        console.print(f"[red]Unknown built-in skill: '{name}'[/red]")
        console.print("Run [cyan]abyss skills install[/cyan] to see available skills.")
        raise typer.Exit(1)
    except FileExistsError:
        console.print(f"[yellow]Skill '{name}' is already installed.[/yellow]")
        raise typer.Exit(1)

    console.print(f"[green]Skill '{name}' installed to {directory}[/green]")

    errors = check_skill_requirements(name)
    if errors:
        console.print("[yellow]Requirements not met (skill remains inactive):[/yellow]")
        for error in errors:
            console.print(f"  [yellow]- {error}[/yellow]")
        console.print(f"Install the missing tools and run: [cyan]abyss skills setup {name}[/cyan]")
    else:
        activate_skill(name)
        console.print(f"[green]All requirements met. Skill '{name}' activated.[/green]")

        # QMD-specific: register conversation logs as a searchable collection
        if name == "qmd":
            from abyss.skill import setup_qmd_conversations_collection

            console.print("Registering conversation logs as QMD collection...")
            if setup_qmd_conversations_collection():
                console.print("[green]Collection 'abyss-conversations' registered.[/green]")


@skill_app.command("import")
def skill_import(
    url: str = typer.Argument(..., help="GitHub repository URL"),
    skill: str = typer.Option(None, "--skill", help="Skill name override (or subdirectory)"),
) -> None:
    """Import a skill from a GitHub repository."""
    from rich.console import Console

    from abyss.skill import (
        activate_skill,
        check_skill_requirements,
        import_skill_from_github,
    )

    console = Console()

    try:
        directory = import_skill_from_github(url, name=skill)
    except ValueError as error:
        console.print(f"[red]Import failed: {error}[/red]")
        raise typer.Exit(1)
    except FileExistsError as error:
        console.print(f"[yellow]{error}[/yellow]")
        raise typer.Exit(1)

    skill_name = directory.name
    console.print(f"[green]Skill '{skill_name}' imported to {directory}[/green]")

    errors = check_skill_requirements(skill_name)
    if errors:
        console.print("[yellow]Requirements not met (skill remains inactive):[/yellow]")
        for error in errors:
            console.print(f"  [yellow]- {error}[/yellow]")
        console.print(
            f"Install the missing tools and run: [cyan]abyss skills setup {skill_name}[/cyan]"
        )
    else:
        activate_skill(skill_name)
        console.print(f"[green]All requirements met. Skill '{skill_name}' activated.[/green]")

    console.print(f"\nAttach to a bot: [cyan]abyss bot skill <bot-name> {skill_name}[/cyan]")


@skill_app.command("add")
def skill_add() -> None:
    """Create a new skill interactively."""
    from rich.console import Console

    from abyss.skill import (
        VALID_SKILL_TYPES,
        create_skill_directory,
        default_skill_yaml,
        generate_skill_markdown,
        is_skill,
        save_skill_config,
    )

    console = Console()

    from abyss.utils import prompt_input

    name = prompt_input("Skill name:")
    if is_skill(name):
        console.print(f"[red]Skill '{name}' already exists.[/red]")
        raise typer.Exit(1)

    description = prompt_input("Description (optional):")

    use_tools = typer.confirm("Does this skill require tools (CLI, MCP, browser)?", default=False)

    selected_type = None
    required_commands: list[str] = []
    environment_variables: list[str] = []

    if use_tools:
        type_choices = ", ".join(VALID_SKILL_TYPES)
        selected_type = prompt_input(f"Skill type ({type_choices}):")
        if selected_type not in VALID_SKILL_TYPES:
            console.print(f"[red]Invalid type: {selected_type}[/red]")
            raise typer.Exit(1)

        commands_input = prompt_input("Required commands (comma-separated, or empty):", default="")
        if commands_input.strip():
            required_commands = [command.strip() for command in commands_input.split(",")]

        environment_variables_input = prompt_input(
            "Environment variables (comma-separated, or empty):", default=""
        )
        if environment_variables_input.strip():
            environment_variables = [
                variable.strip() for variable in environment_variables_input.split(",")
            ]

    directory = create_skill_directory(name)

    skill_markdown = generate_skill_markdown(name, description)
    (directory / "SKILL.md").write_text(skill_markdown)

    if use_tools:
        config = default_skill_yaml(
            name=name,
            description=description,
            skill_type=selected_type,
            required_commands=required_commands if required_commands else None,
            environment_variables=environment_variables if environment_variables else None,
        )
        save_skill_config(name, config)
        console.print(
            f"[green]Skill '{name}' created (type: {selected_type}, status: inactive).[/green]"
        )
        console.print("Run [cyan]abyss skills setup {name}[/cyan] to activate.")
    else:
        activate_skill_directly = True
        if activate_skill_directly:
            console.print(f"[green]Skill '{name}' created (markdown-only, active).[/green]")
        # No skill.yaml needed for markdown-only skills

    console.print(f"  Directory: {directory}")
    console.print(f"  Edit: [cyan]abyss skills edit {name}[/cyan]")


@skill_app.command("remove")
def skill_remove(name: str) -> None:
    """Remove a skill."""
    from rich.console import Console

    from abyss.skill import is_skill, remove_skill

    console = Console()

    if not is_skill(name):
        console.print(f"[red]Skill '{name}' not found.[/red]")
        raise typer.Exit(1)

    confirmed = typer.confirm(f"Remove skill '{name}'? This will detach it from all bots.")
    if not confirmed:
        console.print("[yellow]Cancelled.[/yellow]")
        return

    remove_skill(name)
    console.print(f"[green]Skill '{name}' removed.[/green]")


@skill_app.command("setup")
def skill_setup(name: str) -> None:
    """Set up a skill (check requirements and activate)."""
    from rich.console import Console

    from abyss.skill import (
        activate_skill,
        check_skill_requirements,
        is_skill,
        load_skill_config,
        save_skill_config,
        skill_status,
    )

    console = Console()

    if not is_skill(name):
        console.print(f"[red]Skill '{name}' not found.[/red]")
        raise typer.Exit(1)

    already_active = skill_status(name) == "active"

    # Check if environment variables need configuration (even if already active)
    config = load_skill_config(name)
    has_unconfigured_environment_variables = False
    if config and config.get("environment_variables"):
        environment_variable_values = config.get("environment_variable_values", {})
        for variable in config["environment_variables"]:
            if not environment_variable_values.get(variable):
                has_unconfigured_environment_variables = True
                break

    if already_active and not has_unconfigured_environment_variables:
        console.print(f"[green]Skill '{name}' is already active.[/green]")
        return

    if not already_active:
        errors = check_skill_requirements(name)
        if errors:
            console.print(f"[red]Setup failed for '{name}':[/red]")
            for error in errors:
                console.print(f"  [red]- {error}[/red]")
            raise typer.Exit(1)

    # Prompt for environment variable values if needed
    if config and config.get("environment_variables"):
        from abyss.utils import prompt_input

        environment_variable_values = config.get("environment_variable_values", {})
        for variable in config["environment_variables"]:
            current = environment_variable_values.get(variable, "")
            value = prompt_input(f"  ○ {variable}:", default=current)
            environment_variable_values[variable] = value
        config["environment_variable_values"] = environment_variable_values
        save_skill_config(name, config)

    if not already_active:
        activate_skill(name)
    console.print(f"[green]Skill '{name}' activated.[/green]")

    # QMD-specific: register conversation logs as a searchable collection
    if name == "qmd":
        from abyss.skill import setup_qmd_conversations_collection

        console.print("Registering conversation logs as QMD collection...")
        if setup_qmd_conversations_collection():
            console.print("[green]Collection 'abyss-conversations' registered.[/green]")
        else:
            console.print(
                "[yellow]Could not register collection. "
                "Add manually: qmd collection add ~/.abyss/bots "
                '--name abyss-conversations --mask "**/conversation-*.md"[/yellow]'
            )


@skill_app.command("test")
def skill_test(name: str) -> None:
    """Test a skill's requirements."""
    from rich.console import Console

    from abyss.skill import check_skill_requirements, is_skill

    console = Console()

    if not is_skill(name):
        console.print(f"[red]Skill '{name}' not found.[/red]")
        raise typer.Exit(1)

    errors = check_skill_requirements(name)
    if errors:
        console.print(f"[red]Requirements check failed for '{name}':[/red]")
        for error in errors:
            console.print(f"  [red]- {error}[/red]")
    else:
        console.print(f"[green]All requirements met for '{name}'.[/green]")


@skill_app.command("edit")
def skill_edit(name: str) -> None:
    """Edit a skill's SKILL.md in the default editor."""
    import os
    import subprocess

    from rich.console import Console

    from abyss.skill import is_skill, skill_directory

    console = Console()

    if not is_skill(name):
        console.print(f"[red]Skill '{name}' not found.[/red]")
        raise typer.Exit(1)

    skill_md_path = skill_directory(name) / "SKILL.md"
    editor = os.environ.get("EDITOR", "vi")
    subprocess.run([editor, str(skill_md_path)])


# --- Cron subcommands ---


@cron_app.command("list")
def cron_list(bot: str = typer.Argument(help="Bot name")) -> None:
    """List cron jobs for a bot."""
    from rich.console import Console
    from rich.table import Table

    from abyss.config import load_bot_config
    from abyss.cron import list_cron_jobs, next_run_time

    console = Console()

    if not load_bot_config(bot):
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)

    jobs = list_cron_jobs(bot)
    if not jobs:
        console.print(f"[yellow]No cron jobs for '{bot}'. Run 'abyss cron add {bot}'.[/yellow]")
        return

    table = Table(title=f"Cron Jobs - {bot}")
    table.add_column("Name", style="cyan")
    table.add_column("Schedule", style="magenta")
    table.add_column("Timezone", style="blue")
    table.add_column("Message", style="dim", max_width=40)
    table.add_column("Next Run", style="green")
    table.add_column("Status", style="yellow")

    from abyss.config import get_timezone

    config_timezone = get_timezone()

    for job in jobs:
        schedule_display = job.get("schedule") or f"at: {job.get('at', 'N/A')}"
        timezone_label = job.get("timezone", config_timezone)
        enabled = job.get("enabled", True)
        status = "enabled" if enabled else "disabled"
        status_style = "green" if enabled else "red"

        next_time = next_run_time(job) if enabled else None
        next_display = next_time.strftime("%Y-%m-%d %H:%M") if next_time else "-"

        message = job.get("message", "")
        if len(message) > 40:
            message = message[:37] + "..."

        table.add_row(
            job.get("name", ""),
            schedule_display,
            timezone_label,
            message,
            next_display,
            f"[{status_style}]{status}[/{status_style}]",
        )

    console.print(table)


@cron_app.command("add")
def cron_add(bot: str = typer.Argument(help="Bot name")) -> None:
    """Add a cron job to a bot interactively."""
    from rich.console import Console

    from abyss.config import load_bot_config
    from abyss.cron import (
        add_cron_job,
        get_cron_job,
        parse_one_shot_time,
        validate_cron_schedule,
    )

    console = Console()

    if not load_bot_config(bot):
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)

    from abyss.utils import prompt_input, prompt_multiline

    name = prompt_input("Job name:")
    if get_cron_job(bot, name):
        console.print(f"[red]Job '{name}' already exists.[/red]")
        raise typer.Exit(1)

    use_one_shot = typer.confirm("One-shot (run once at specific time)?", default=False)

    job: dict = {"name": name, "enabled": True}

    if use_one_shot:
        at_value = prompt_input("Run at (ISO datetime or duration like 30m/2h/1d):")
        parsed = parse_one_shot_time(at_value)
        if not parsed:
            console.print(f"[red]Invalid time: {at_value}[/red]")
            raise typer.Exit(1)
        job["at"] = at_value
        delete_after = typer.confirm("Delete after run?", default=True)
        job["delete_after_run"] = delete_after
    else:
        schedule = prompt_input("Cron schedule (e.g. '0 9 * * *' for daily 9am):")
        if not validate_cron_schedule(schedule):
            console.print(f"[red]Invalid cron expression: {schedule}[/red]")
            raise typer.Exit(1)
        job["schedule"] = schedule

        from abyss.config import get_timezone

        default_timezone = get_timezone()
        timezone_input = prompt_input(
            f"Timezone (e.g. Asia/Seoul, UTC) [{default_timezone}]:", default=default_timezone
        )
        job["timezone"] = timezone_input

    message = prompt_multiline("Message to send to Claude:")
    job["message"] = message

    skills_input = prompt_input("Skills (comma-separated, or empty):", default="")
    if skills_input.strip():
        job["skills"] = [skill.strip() for skill in skills_input.split(",")]

    model_input = prompt_input("Model (sonnet/opus/haiku, or empty for bot default):", default="")
    if model_input.strip():
        from abyss.config import is_valid_model

        if not is_valid_model(model_input.strip()):
            console.print(f"[red]Invalid model: {model_input}[/red]")
            raise typer.Exit(1)
        job["model"] = model_input.strip()

    add_cron_job(bot, job)
    console.print(f"[green]Cron job '{name}' added to '{bot}'.[/green]")


@cron_app.command("remove")
def cron_remove(
    bot: str = typer.Argument(help="Bot name"),
    job: str = typer.Argument(help="Job name"),
) -> None:
    """Remove a cron job."""
    from rich.console import Console

    from abyss.cron import remove_cron_job

    console = Console()

    if not remove_cron_job(bot, job):
        console.print(f"[red]Job '{job}' not found in bot '{bot}'.[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Job '{job}' removed from '{bot}'.[/green]")


@cron_app.command("enable")
def cron_enable(
    bot: str = typer.Argument(help="Bot name"),
    job: str = typer.Argument(help="Job name"),
) -> None:
    """Enable a cron job."""
    from rich.console import Console

    from abyss.cron import enable_cron_job

    console = Console()

    if not enable_cron_job(bot, job):
        console.print(f"[red]Job '{job}' not found in bot '{bot}'.[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Job '{job}' enabled.[/green]")


@cron_app.command("disable")
def cron_disable(
    bot: str = typer.Argument(help="Bot name"),
    job: str = typer.Argument(help="Job name"),
) -> None:
    """Disable a cron job."""
    from rich.console import Console

    from abyss.cron import disable_cron_job

    console = Console()

    if not disable_cron_job(bot, job):
        console.print(f"[red]Job '{job}' not found in bot '{bot}'.[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Job '{job}' disabled.[/green]")


@cron_app.command("edit")
def cron_edit(
    bot: str = typer.Argument(help="Bot name"),
    job: str = typer.Argument(help="Job name"),
) -> None:
    """Edit a cron job message in $EDITOR."""
    import click
    from rich.console import Console

    from abyss.cron import edit_cron_job_message, get_cron_job

    console = Console()

    cron_job = get_cron_job(bot, job)
    if not cron_job:
        console.print(f"[red]Job '{job}' not found in bot '{bot}'.[/red]")
        raise typer.Exit(1)

    current_message = cron_job.get("message", "")
    edited = click.edit(current_message)

    if edited is None:
        console.print("[yellow]Edit cancelled.[/yellow]")
        return

    new_message = edited.strip()
    if new_message == current_message:
        console.print("[yellow]No changes made.[/yellow]")
        return

    edit_cron_job_message(bot, job, new_message)
    console.print(f"[green]Job '{job}' message updated.[/green]")


@cron_app.command("run")
def cron_run(
    bot: str = typer.Argument(help="Bot name"),
    job: str = typer.Argument(help="Job name"),
) -> None:
    """Run a cron job immediately (for testing)."""
    import asyncio

    from rich.console import Console

    from abyss.claude_runner import run_claude
    from abyss.config import DEFAULT_MODEL, load_bot_config
    from abyss.cron import cron_session_directory, get_cron_job

    console = Console()

    bot_config = load_bot_config(bot)
    if not bot_config:
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)

    cron_job = get_cron_job(bot, job)
    if not cron_job:
        console.print(f"[red]Job '{job}' not found in bot '{bot}'.[/red]")
        raise typer.Exit(1)

    message = cron_job.get("message", "")
    model = cron_job.get("model") or bot_config.get("model", DEFAULT_MODEL)
    job_skills = cron_job.get("skills") or bot_config.get("skills", [])
    command_timeout = bot_config.get("command_timeout", 300)
    working_directory = str(cron_session_directory(bot, job))

    console.print(f"[cyan]Running job '{job}'...[/cyan]")
    console.print(f"  Message: {message}")
    console.print(f"  Model: {model}")

    async def _run() -> str:
        return await run_claude(
            working_directory=working_directory,
            message=message,
            timeout=command_timeout,
            session_key=f"cron:{bot}:{job}",
            model=model,
            skill_names=job_skills if job_skills else None,
        )

    try:
        response = asyncio.run(_run())
        console.print(f"\n[green]Result:[/green]\n{response}")
    except Exception as error:
        console.print(f"[red]Error: {error}[/red]")
        raise typer.Exit(1)


# --- Memory subcommands ---


@memory_app.command("show")
def memory_show(bot: str = typer.Argument(help="Bot name")) -> None:
    """Show bot memory contents."""
    from rich.console import Console
    from rich.markdown import Markdown

    from abyss.config import bot_directory, load_bot_config
    from abyss.session import load_bot_memory

    console = Console()

    if not load_bot_config(bot):
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)

    content = load_bot_memory(bot_directory(bot))
    if not content:
        console.print(f"[yellow]No memories saved for '{bot}'.[/yellow]")
        return

    console.print(Markdown(content))


@memory_app.command("edit")
def memory_edit(bot: str = typer.Argument(help="Bot name")) -> None:
    """Edit bot memory in the default editor."""
    import os
    import subprocess

    from rich.console import Console

    from abyss.config import bot_directory, load_bot_config
    from abyss.session import memory_file_path

    console = Console()

    if not load_bot_config(bot):
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)

    path = memory_file_path(bot_directory(bot))
    if not path.exists():
        path.write_text("# Memory\n\n")

    editor = os.environ.get("EDITOR", "vi")
    subprocess.run([editor, str(path)])


@memory_app.command("clear")
def memory_clear(bot: str = typer.Argument(help="Bot name")) -> None:
    """Clear bot memory."""
    from rich.console import Console

    from abyss.config import bot_directory, load_bot_config
    from abyss.session import clear_bot_memory

    console = Console()

    if not load_bot_config(bot):
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)

    confirmed = typer.confirm(f"Clear all memory for '{bot}'?")
    if not confirmed:
        console.print("[yellow]Cancelled.[/yellow]")
        return

    clear_bot_memory(bot_directory(bot))
    console.print(f"[green]Memory cleared for '{bot}'.[/green]")


# --- Global memory subcommands ---


def _regenerate_all_bots_claude_md() -> None:
    """Regenerate CLAUDE.md for all bots and propagate to sessions."""
    from abyss.config import bot_directory, load_config
    from abyss.skill import regenerate_bot_claude_md, update_session_claude_md

    config = load_config()
    if not config or not config.get("bots"):
        return

    for bot_entry in config["bots"]:
        name = bot_entry["name"]
        regenerate_bot_claude_md(name)
        update_session_claude_md(bot_directory(name))


@global_memory_app.command("show")
def global_memory_show() -> None:
    """Show global memory contents."""
    from rich.console import Console
    from rich.markdown import Markdown

    from abyss.session import load_global_memory

    console = Console()

    content = load_global_memory()
    if not content:
        console.print("[yellow]No global memory saved yet.[/yellow]")
        return

    console.print(Markdown(content))


@global_memory_app.command("edit")
def global_memory_edit() -> None:
    """Edit global memory in the default editor."""
    import os
    import subprocess

    from rich.console import Console

    from abyss.session import global_memory_file_path, save_global_memory

    console = Console()

    path = global_memory_file_path()
    if not path.exists():
        save_global_memory("# Global Memory\n\n")

    editor = os.environ.get("EDITOR", "vi")
    subprocess.run([editor, str(path)])

    # Regenerate all bots' CLAUDE.md to include updated global memory
    _regenerate_all_bots_claude_md()
    console.print("[green]Global memory updated. All bots' CLAUDE.md regenerated.[/green]")


@global_memory_app.command("clear")
def global_memory_clear() -> None:
    """Clear global memory."""
    from rich.console import Console

    from abyss.session import clear_global_memory

    console = Console()

    confirmed = typer.confirm("Clear global memory? This affects all bots.")
    if not confirmed:
        console.print("[yellow]Cancelled.[/yellow]")
        return

    clear_global_memory()
    _regenerate_all_bots_claude_md()
    console.print("[green]Global memory cleared. All bots' CLAUDE.md regenerated.[/green]")


# --- Heartbeat subcommands ---


@heartbeat_app.command("status")
def heartbeat_status() -> None:
    """Show heartbeat status for all bots."""
    from rich.console import Console
    from rich.table import Table

    from abyss.config import DEFAULT_MODEL, load_bot_config, load_config
    from abyss.heartbeat import get_heartbeat_config

    console = Console()
    config = load_config()

    if not config or not config.get("bots"):
        console.print("[yellow]No bots configured.[/yellow]")
        return

    table = Table(title="Heartbeat Status")
    table.add_column("Bot", style="cyan")
    table.add_column("Enabled", style="green")
    table.add_column("Interval", style="magenta")
    table.add_column("Active Hours", style="dim")
    table.add_column("Model", style="yellow")

    for bot_entry in config["bots"]:
        name = bot_entry["name"]
        bot_config = load_bot_config(name)
        if not bot_config:
            continue

        heartbeat_config = get_heartbeat_config(name)
        enabled = heartbeat_config.get("enabled", False)
        interval = heartbeat_config.get("interval_minutes", 30)
        active_hours = heartbeat_config.get("active_hours", {})
        start = active_hours.get("start", "07:00")
        end = active_hours.get("end", "23:00")
        model = bot_config.get("model", DEFAULT_MODEL)

        enabled_display = "[green]on[/green]" if enabled else "[red]off[/red]"
        table.add_row(name, enabled_display, f"{interval}m", f"{start}-{end}", model)

    console.print(table)


@heartbeat_app.command("enable")
def heartbeat_enable(bot: str = typer.Argument(help="Bot name")) -> None:
    """Enable heartbeat for a bot."""
    from rich.console import Console

    from abyss.config import load_bot_config
    from abyss.heartbeat import enable_heartbeat

    console = Console()

    if not load_bot_config(bot):
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)

    if enable_heartbeat(bot):
        console.print(f"[green]Heartbeat enabled for '{bot}'.[/green]")
    else:
        console.print(f"[red]Failed to enable heartbeat for '{bot}'.[/red]")
        raise typer.Exit(1)


@heartbeat_app.command("disable")
def heartbeat_disable(bot: str = typer.Argument(help="Bot name")) -> None:
    """Disable heartbeat for a bot."""
    from rich.console import Console

    from abyss.config import load_bot_config
    from abyss.heartbeat import disable_heartbeat

    console = Console()

    if not load_bot_config(bot):
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)

    if disable_heartbeat(bot):
        console.print(f"[green]Heartbeat disabled for '{bot}'.[/green]")
    else:
        console.print(f"[red]Failed to disable heartbeat for '{bot}'.[/red]")
        raise typer.Exit(1)


@heartbeat_app.command("run")
def heartbeat_run(bot: str = typer.Argument(help="Bot name")) -> None:
    """Run heartbeat immediately (for testing)."""
    import asyncio

    from rich.console import Console

    from abyss.claude_runner import run_claude
    from abyss.config import DEFAULT_MODEL, load_bot_config
    from abyss.heartbeat import (
        HEARTBEAT_OK_MARKER,
        heartbeat_session_directory,
        load_heartbeat_markdown,
    )

    console = Console()

    bot_config = load_bot_config(bot)
    if not bot_config:
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)

    heartbeat_content = load_heartbeat_markdown(bot)
    if not heartbeat_content:
        console.print(
            f"[yellow]No HEARTBEAT.md found. Run 'abyss heartbeat enable {bot}' first.[/yellow]"
        )
        raise typer.Exit(1)

    model = bot_config.get("model", DEFAULT_MODEL)
    attached_skills = bot_config.get("skills", [])
    command_timeout = bot_config.get("command_timeout", 300)
    working_directory = str(heartbeat_session_directory(bot))

    message = f"다음 체크리스트를 확인하고 결과를 알려주세요.\n\n{heartbeat_content}"

    console.print(f"[cyan]Running heartbeat for '{bot}'...[/cyan]")
    console.print(f"  Model: {model}")

    async def _run() -> str:
        return await run_claude(
            working_directory=working_directory,
            message=message,
            timeout=command_timeout,
            session_key=f"heartbeat:{bot}",
            model=model,
            skill_names=attached_skills if attached_skills else None,
        )

    try:
        response = asyncio.run(_run())
        if HEARTBEAT_OK_MARKER in response:
            console.print("\n[green]Result: HEARTBEAT_OK (no notification needed)[/green]")
        else:
            console.print("\n[yellow]Result: notification would be sent[/yellow]")
        console.print(f"\n{response}")
    except Exception as error:
        console.print(f"[red]Error: {error}[/red]")
        raise typer.Exit(1)


@heartbeat_app.command("edit")
def heartbeat_edit(bot: str = typer.Argument(help="Bot name")) -> None:
    """Edit HEARTBEAT.md for a bot."""
    import os
    import subprocess

    from rich.console import Console

    from abyss.config import load_bot_config
    from abyss.heartbeat import (
        default_heartbeat_content,
        heartbeat_session_directory,
    )

    console = Console()

    if not load_bot_config(bot):
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)

    session_directory = heartbeat_session_directory(bot)
    heartbeat_md_path = session_directory / "HEARTBEAT.md"

    if not heartbeat_md_path.exists():
        heartbeat_md_path.write_text(default_heartbeat_content())

    editor = os.environ.get("EDITOR", "vi")
    subprocess.run([editor, str(heartbeat_md_path)])


# --- Group commands ---


@group_app.command("create")
def group_create(
    name: str = typer.Argument(help="Group name"),
    orchestrator: str = typer.Option(..., "--orchestrator", "-o", help="Orchestrator bot name"),
    members: str = typer.Option(..., "--members", "-m", help="Comma-separated member bot names"),
) -> None:
    """Create a new group for multi-bot collaboration."""
    from rich.console import Console

    from abyss.group import create_group

    console = Console()
    member_list = [m.strip() for m in members.split(",") if m.strip()]

    if not member_list:
        console.print("[red]At least one member is required.[/red]")
        raise typer.Exit(1)

    try:
        create_group(name=name, orchestrator=orchestrator, members=member_list)
    except ValueError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Group '{name}' created.[/green]")
    console.print(f"  Orchestrator: [cyan]{orchestrator}[/cyan]")
    console.print(f"  Members: [cyan]{', '.join(member_list)}[/cyan]")
    console.print(
        f"\nNext: Add bots to a Telegram group, then run [green]/bind {name}[/green] in the group."
    )


@group_app.command("list")
def group_list() -> None:
    """List all groups."""
    from rich.console import Console
    from rich.table import Table

    from abyss.group import list_groups

    console = Console()
    groups = list_groups()

    if not groups:
        console.print("[yellow]No groups configured. Run 'abyss group create'.[/yellow]")
        return

    table = Table(title="Groups")
    table.add_column("Name", style="cyan")
    table.add_column("Orchestrator", style="magenta")
    table.add_column("Members", style="white")
    table.add_column("Telegram", style="dim")

    for group_config in groups:
        chat_id = group_config.get("telegram_chat_id")
        telegram_status = f"bound ({chat_id})" if chat_id else "not bound"
        table.add_row(
            group_config["name"],
            group_config["orchestrator"],
            ", ".join(group_config.get("members", [])),
            telegram_status,
        )

    console.print(table)


@group_app.command("show")
def group_show(name: str = typer.Argument(help="Group name")) -> None:
    """Show group details."""
    from rich.console import Console

    from abyss.config import load_bot_config
    from abyss.group import list_workspace_files, load_group_config

    console = Console()
    group_config = load_group_config(name)

    if not group_config:
        console.print(f"[red]Group '{name}' not found.[/red]")
        raise typer.Exit(1)

    chat_id = group_config.get("telegram_chat_id")
    telegram_status = f"{chat_id} (bound)" if chat_id else "not bound"

    console.print(f"[bold]Name:[/bold] [cyan]{group_config['name']}[/cyan]")

    orchestrator_name = group_config["orchestrator"]
    orchestrator_config = load_bot_config(orchestrator_name)
    orchestrator_username = ""
    if orchestrator_config:
        orchestrator_username = f" ({orchestrator_config.get('telegram_username', '')})"
    console.print(
        f"[bold]Orchestrator:[/bold] [magenta]{orchestrator_name}{orchestrator_username}[/magenta]"
    )

    member_parts: list[str] = []
    for member_name in group_config.get("members", []):
        member_config = load_bot_config(member_name)
        if member_config:
            username = member_config.get("telegram_username", "")
            member_parts.append(f"{member_name} ({username})")
        else:
            member_parts.append(member_name)
    console.print(f"[bold]Members:[/bold] {', '.join(member_parts)}")

    console.print(f"[bold]Telegram:[/bold] {telegram_status}")

    workspace_files = list_workspace_files(name)
    console.print(f"[bold]Workspace:[/bold] {len(workspace_files)} files")


@group_app.command("delete")
def group_delete(name: str = typer.Argument(help="Group name")) -> None:
    """Delete a group and all its data."""
    from rich.console import Console

    from abyss.group import delete_group, load_group_config

    console = Console()

    if not load_group_config(name):
        console.print(f"[red]Group '{name}' not found.[/red]")
        raise typer.Exit(1)

    confirmed = typer.confirm(f"Delete group '{name}'? This will remove all group data.")
    if not confirmed:
        console.print("[yellow]Cancelled.[/yellow]")
        return

    try:
        delete_group(name)
    except ValueError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Group '{name}' deleted.[/green]")


@group_app.command("status")
def group_status(
    name: str | None = typer.Argument(default=None, help="Group name (omit to list all groups)"),
) -> None:
    """Show group status. Detailed if GROUP_NAME given; otherwise all."""
    import os

    from rich.console import Console
    from rich.table import Table

    from abyss.config import abyss_home
    from abyss.group import (
        list_groups,
        list_workspace_files,
        load_group_config,
        load_shared_conversation,
    )

    console = Console()

    def _is_daemon_running() -> bool:
        """Return True if the abyss daemon/process is running."""
        from pathlib import Path

        pid_file = abyss_home() / "abyss.pid"
        plist_path = Path.home() / "Library" / "LaunchAgents" / "com.abyss.daemon.plist"
        if plist_path.exists():
            return True
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                os.kill(pid, 0)
                return True
            except (ValueError, ProcessLookupError, OSError, OverflowError):
                return False
        return False

    def _bot_status_icon(bot_name: str, daemon_running: bool) -> str:
        """Return 🟢 if daemon is running and bot is in config, else 🔴."""
        from abyss.config import bot_exists

        if daemon_running and bot_exists(bot_name):
            return "🟢"
        return "🔴"

    if name is not None:
        # --- Detailed view for a single group ---
        group_config = load_group_config(name)
        if not group_config:
            console.print(f"[red]Group '{name}' not found.[/red]")
            raise typer.Exit(1)

        daemon_running = _is_daemon_running()

        chat_id = group_config.get("telegram_chat_id")
        if chat_id:
            telegram_status = f"[green]bound ({chat_id})[/green]"
        else:
            telegram_status = "[yellow]not bound[/yellow]"

        console.print(f"[bold]Name:[/bold] [cyan]{group_config['name']}[/cyan]")
        console.print(f"[bold]Telegram:[/bold] {telegram_status}")

        orchestrator_name = group_config["orchestrator"]
        orch_icon = _bot_status_icon(orchestrator_name, daemon_running)
        console.print(
            f"[bold]Orchestrator:[/bold] {orch_icon} [magenta]{orchestrator_name}[/magenta]"
        )

        members = group_config.get("members", [])
        if members:
            console.print("[bold]Members:[/bold]")
            for member_name in members:
                member_icon = _bot_status_icon(member_name, daemon_running)
                console.print(f"  {member_icon} [white]{member_name}[/white]")
        else:
            console.print("[bold]Members:[/bold] [dim](none)[/dim]")

        workspace_files = list_workspace_files(name)
        console.print(f"[bold]Workspace files:[/bold] [cyan]{len(workspace_files)}[/cyan]")

        console.print("[bold]Recent conversation:[/bold]")
        conversation = load_shared_conversation(name, max_lines=5)
        if conversation:
            for line in conversation.strip().splitlines()[-5:]:
                console.print(f"  [dim]{line}[/dim]")
        else:
            console.print("  [dim]No recent activity[/dim]")

    else:
        # --- Summary table for all groups ---
        groups = list_groups()

        if not groups:
            console.print("[yellow]No groups configured. Run 'abyss group create'.[/yellow]")
            return

        daemon_running = _is_daemon_running()

        table = Table(title="Group Status")
        table.add_column("Name", style="cyan")
        table.add_column("Orchestrator", style="magenta")
        table.add_column("Members", style="white")
        table.add_column("Bots Running", justify="center")
        table.add_column("Telegram", style="dim")

        for group_config in groups:
            group_name = group_config["name"]
            orchestrator_name = group_config["orchestrator"]
            members = group_config.get("members", [])
            all_bots = [orchestrator_name, *members]

            from abyss.config import bot_exists

            running_count = sum(1 for bot in all_bots if daemon_running and bot_exists(bot))
            total_count = len(all_bots)
            running_label = f"[green]{running_count}[/green]/[white]{total_count}[/white]"

            chat_id = group_config.get("telegram_chat_id")
            telegram_status = f"bound ({chat_id})" if chat_id else "not bound"

            table.add_row(
                group_name,
                orchestrator_name,
                ", ".join(members) if members else "[dim](none)[/dim]",
                running_label,
                telegram_status,
            )

        console.print(table)
