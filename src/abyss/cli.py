"""abyss CLI - Typer application entry point."""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(
    help="abyss - Personal AI assistant via PWA + Claude Code",
    invoke_without_command=True,
)


ASCII_ART = r"""
  █████╗ ██████╗ ██╗   ██╗███████╗███████╗
 ██╔══██╗██╔══██╗╚██╗ ██╔╝██╔════╝██╔════╝
 ███████║██████╔╝ ╚████╔╝ ███████╗███████╗
 ██╔══██║██╔══██╗  ╚██╔╝  ╚════██║╚════██║
 ██║  ██║██████╔╝   ██║   ███████║███████║
 ╚═╝  ╚═╝╚═════╝    ╚═╝   ╚══════╝╚══════╝
  Personal AI assistant — PWA + Claude Code
"""


@app.callback()
def main(context: typer.Context) -> None:
    """abyss - Personal AI assistant via PWA + Claude Code."""
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
skill_proposals_app = typer.Typer(
    help="Bot-proposed skill suggestions (Phase 5 of co-evolution)",
)
skill_app.add_typer(skill_proposals_app, name="proposals")
cron_app = typer.Typer(help="Cron job management")
app.add_typer(cron_app, name="cron")
memory_app = typer.Typer(help="Bot memory management")
app.add_typer(memory_app, name="memory")
global_memory_app = typer.Typer(help="Global memory management (shared across all bots)")
app.add_typer(global_memory_app, name="global-memory")
heartbeat_app = typer.Typer(help="Heartbeat management")
app.add_typer(heartbeat_app, name="heartbeat")
feedback_app = typer.Typer(help="Numeric feedback (1/2/3) statistics")
app.add_typer(feedback_app, name="feedback")
about_me_app = typer.Typer(help="Shared user knowledge base (ABOUT_ME/)")
app.add_typer(about_me_app, name="about-me")
self_app = typer.Typer(help="Per-bot self-reflection (SELF.md)")
app.add_typer(self_app, name="self")
episodes_app = typer.Typer(help="Per-bot episodic timeline (episodes.jsonl)")
app.add_typer(episodes_app, name="episodes")
facts_app = typer.Typer(help="Per-bot structured facts (facts.db)")
app.add_typer(facts_app, name="facts")


@app.command()
def init() -> None:
    """Run initial setup wizard."""
    from abyss.onboarding import run_onboarding

    run_onboarding()


@app.command()
def start(
    bot: str = typer.Option(None, help="Start specific bot only"),
    daemon: bool = typer.Option(
        False,
        "--daemon",
        "-d",
        help="Run as a launchd background daemon. Foreground by default so "
        "the boot checklist is visible in the terminal.",
    ),
    port: int = typer.Option(
        3847,
        "--port",
        "-p",
        help="Port for the abysscope dashboard frontend (default 3847).",
    ),
) -> None:
    """Start abyss (API server + dashboard + per-bot schedulers).

    Foreground by default — the Rich ``BuildProgress`` checklist
    renders live in the terminal. Press Ctrl+C to stop. Use
    ``--daemon`` to register a launchd job and detach.
    """
    from abyss.bot_manager import start_bots

    start_bots(bot_name=bot, daemon=daemon, dashboard_port=port)


@app.command()
def stop() -> None:
    """Stop abyss (daemon, API server, dashboard, schedulers)."""
    from abyss.bot_manager import stop_bots

    stop_bots()


@app.command()
def restart(
    bot: str = typer.Option(None, help="Restart specific bot only"),
    daemon: bool = typer.Option(
        False,
        "--daemon",
        "-d",
        help="Run as a launchd background daemon. Foreground by default so "
        "the boot checklist is visible in the terminal.",
    ),
    port: int = typer.Option(
        3847,
        "--port",
        "-p",
        help="Port for the abysscope dashboard frontend (default 3847).",
    ),
) -> None:
    """Restart abyss. Stops then starts."""
    from abyss.bot_manager import start_bots, stop_bots

    stop_bots()
    start_bots(bot_name=bot, daemon=daemon, dashboard_port=port)


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
    all_scopes: bool = typer.Option(False, "--all", help="Rebuild every bot's conversation index."),
) -> None:
    """Rebuild SQLite FTS5 conversation indexes from markdown logs.

    Markdown is the source of truth — this command wipes the affected
    DB and re-inserts every parsed message. Safe to run repeatedly.

    The ``--group`` scope was retired alongside the group surface.
    """
    from rich.console import Console

    from abyss import conversation_index
    from abyss.config import bot_directory, load_config

    console = Console()

    if not conversation_index.is_fts5_available():
        console.print("[red]SQLite FTS5 is not available — cannot reindex.[/red]")
        raise typer.Exit(code=1)

    selected_bots: list[str] = []
    if bot:
        selected_bots = [bot]
    if all_scopes:
        config = load_config() or {}
        selected_bots = [entry["name"] for entry in config.get("bots", [])]

    if not selected_bots:
        console.print("[yellow]Specify --bot NAME or --all.[/yellow]")
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
    table.add_column("Display Name", style="green")
    table.add_column("Model", style="magenta")
    table.add_column("Path", style="dim")

    for bot_entry in config["bots"]:
        from abyss.config import DEFAULT_MODEL, bot_directory, load_bot_config

        bot_config = load_bot_config(bot_entry["name"]) or {}
        display_name = bot_config.get("display_name") or bot_entry["name"]
        model = bot_config.get("model", DEFAULT_MODEL)
        path = str(bot_directory(bot_entry["name"]))
        table.add_row(bot_entry["name"], display_name, model, path)

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
    """Run a cron job immediately (for testing).

    Calls ``execute_cron_job`` — the same function the scheduler
    invokes — so the run logs to ``conversation-*.md``, updates the
    FTS5 index, and fires a Web Push notification (when a PWA
    subscription exists). The Routines tab will pick up the result
    the next time it refreshes.
    """
    import asyncio

    from rich.console import Console

    from abyss.config import load_bot_config
    from abyss.cron import execute_cron_job, get_cron_job

    console = Console()

    bot_config = load_bot_config(bot)
    if not bot_config:
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)

    cron_job = get_cron_job(bot, job)
    if not cron_job:
        console.print(f"[red]Job '{job}' not found in bot '{bot}'.[/red]")
        raise typer.Exit(1)

    console.print(f"[cyan]Running cron '{job}' for bot '{bot}'...[/cyan]")
    try:
        asyncio.run(execute_cron_job(bot_name=bot, job=cron_job, bot_config=bot_config))
    except Exception as error:
        console.print(f"[red]Error: {error}[/red]")
        raise typer.Exit(1) from error
    console.print(
        "\n[green]Done.[/green] Check the mobile Routines tab or the "
        f"``conversation-*.md`` file under ``cron_sessions/{job}/`` for the reply."
    )


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


# --- Feedback subcommands ---


@feedback_app.command("show")
def feedback_show(
    bot: str = typer.Argument(help="Bot name"),
    last_n: int = typer.Option(10, "--last", "-n", help="How many recent entries"),
) -> None:
    """Show numeric feedback (1/2/3) statistics for a bot."""
    from rich.console import Console
    from rich.table import Table

    from abyss.config import load_bot_config
    from abyss.feedback import SIGNAL_LABELS, aggregate

    console = Console()

    if not load_bot_config(bot):
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)

    summary = aggregate(bot, last_n=last_n)
    total = summary["total"]

    if total == 0:
        console.print(f"[yellow]No feedback yet for '{bot}'.[/yellow]")
        return

    console.print(f"\n[bold]Feedback for:[/bold] {bot}")
    console.print(f"[bold]Total:[/bold] {total}\n")

    counts = summary["count_by_signal"]
    table = Table(show_header=True, header_style="bold")
    table.add_column("Signal")
    table.add_column("Label")
    table.add_column("Count", justify="right")
    table.add_column("Pct", justify="right")
    for signal, label in SIGNAL_LABELS.items():
        count = counts.get(signal, 0)
        pct = (count / total) * 100 if total else 0.0
        table.add_row(str(signal), label, str(count), f"{pct:.1f}%")
    console.print(table)

    entries = summary["last_entries"]
    if entries:
        console.print(f"\n[bold]Last {len(entries)} entries:[/bold]")
        recent = Table(show_header=True, header_style="bold")
        recent.add_column("Timestamp (UTC)")
        recent.add_column("Session")
        recent.add_column("Signal", justify="right")
        recent.add_column("Note")
        for entry in entries:
            ts = entry.get("ts", "")
            session_id = entry.get("session_id", "")
            signal = entry.get("signal", "")
            note = entry.get("note", "") or ""
            if len(note) > 40:
                note = note[:37] + "..."
            recent.add_row(ts, session_id, str(signal), note)
        console.print(recent)


# --- Self reflection subcommands ---


@self_app.command("show")
def self_show(bot: str = typer.Argument(help="Bot name")) -> None:
    """Print the bot's SELF.md (empty notice if missing)."""
    from rich.console import Console
    from rich.markdown import Markdown

    from abyss.config import load_bot_config
    from abyss.self_reflection import load_self_md

    console = Console()
    if not load_bot_config(bot):
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)
    content = load_self_md(bot)
    if not content.strip():
        console.print(f"[yellow]SELF.md is empty for '{bot}'.[/yellow]")
        return
    console.print(Markdown(content))


@self_app.command("reflect")
def self_reflect(bot: str = typer.Argument(help="Bot name")) -> None:
    """Run one reflection turn now and overwrite SELF.md."""
    import asyncio

    from rich.console import Console

    from abyss.config import load_bot_config
    from abyss.self_reflection import run_reflection

    console = Console()
    config = load_bot_config(bot)
    if not config:
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)
    console.print(f"[cyan]Running reflection for {bot}…[/cyan]")
    asyncio.run(run_reflection(bot, config))
    console.print(f"[green]SELF.md updated for {bot}.[/green]")


@self_app.command("schedule")
def self_schedule(
    bot: str = typer.Argument(help="Bot name"),
    cron_expr: str = typer.Option(
        None,
        "--cron",
        "-c",
        help="Cron schedule (default: weekly Sunday 04:00)",
    ),
) -> None:
    """Register the weekly self-reflection cron job for ``bot``."""
    from rich.console import Console

    from abyss.config import load_bot_config
    from abyss.cron import add_cron_job, get_cron_job
    from abyss.self_reflection import DEFAULT_REFLECTION_CRON, REFLECTION_JOB_NAME

    console = Console()
    if not load_bot_config(bot):
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)
    if get_cron_job(bot, REFLECTION_JOB_NAME):
        console.print(
            f"[yellow]'{REFLECTION_JOB_NAME}' already scheduled for {bot}. "
            "Unschedule first to change cadence.[/yellow]"
        )
        raise typer.Exit(1)
    schedule = (cron_expr or DEFAULT_REFLECTION_CRON).strip()
    add_cron_job(
        bot,
        {
            "name": REFLECTION_JOB_NAME,
            "schedule": schedule,
            "enabled": True,
            "message": (
                "Run weekly self-reflection. Update SELF.md based on the "
                "recent conversation log and feedback aggregate."
            ),
        },
    )
    console.print(
        f"[green]Scheduled '{REFLECTION_JOB_NAME}' for {bot} (cron='{schedule}').[/green]"
    )


@self_app.command("unschedule")
def self_unschedule(bot: str = typer.Argument(help="Bot name")) -> None:
    """Remove the self-reflection cron job for ``bot``."""
    from rich.console import Console

    from abyss.config import load_bot_config
    from abyss.cron import remove_cron_job
    from abyss.self_reflection import REFLECTION_JOB_NAME

    console = Console()
    if not load_bot_config(bot):
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)
    if remove_cron_job(bot, REFLECTION_JOB_NAME):
        console.print(f"[green]Removed '{REFLECTION_JOB_NAME}' from {bot}.[/green]")
    else:
        console.print(f"[yellow]No '{REFLECTION_JOB_NAME}' job to remove for {bot}.[/yellow]")


# --- Skill proposals subcommands (Phase 5) ---


@skill_proposals_app.command("show")
def skill_proposals_show(
    bot: str = typer.Argument(help="Bot name"),
    status: str = typer.Option(None, "--status", help="Filter by pending|approved|rejected"),
) -> None:
    """Print pending skill proposals the bot made for human review."""
    from rich.console import Console
    from rich.table import Table

    from abyss.config import load_bot_config
    from abyss.skill_proposals import list_proposals

    console = Console()
    if not load_bot_config(bot):
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)
    rows = list_proposals(bot, status=status)
    if not rows:
        console.print(f"[yellow]No proposals for '{bot}'.[/yellow]")
        return
    table = Table(title=f"Skill proposals — {bot}")
    table.add_column("ID")
    table.add_column("URL")
    table.add_column("Reasons")
    table.add_column("Status")
    table.add_column("Proposed at")
    for row in rows:
        reasons = "\n".join(row.reasons) if row.reasons else "(none)"
        table.add_row(row.id, row.candidate_url, reasons, row.status, row.proposed_at)
    console.print(table)


@skill_proposals_app.command("approve")
def skill_proposals_approve(
    bot: str = typer.Argument(help="Bot name"),
    proposal_id: str = typer.Argument(help="Proposal id (see ``skills proposals show``)"),
) -> None:
    """Approve a proposal — clones the GitHub skill and attaches it to the bot."""
    from rich.console import Console

    from abyss.config import load_bot_config
    from abyss.skill_proposals import approve

    console = Console()
    if not load_bot_config(bot):
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)
    result = approve(bot, proposal_id)
    if not result.get("ok"):
        console.print(
            f"[red]Approve failed at '{result.get('stage', '?')}': {result.get('error')}[/red]"
        )
        raise typer.Exit(1)
    if result.get("noop"):
        console.print(f"[yellow]Proposal {proposal_id} was already approved.[/yellow]")
        return
    console.print(
        f"[green]Approved — installed '{result['skill_name']}' and attached to {bot}.[/green]"
    )


@skill_proposals_app.command("reject")
def skill_proposals_reject(
    bot: str = typer.Argument(help="Bot name"),
    proposal_id: str = typer.Argument(help="Proposal id"),
) -> None:
    """Reject a proposal — bot will not re-propose the same URL."""
    from rich.console import Console

    from abyss.config import load_bot_config
    from abyss.skill_proposals import reject

    console = Console()
    if not load_bot_config(bot):
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)
    updated = reject(bot, proposal_id)
    if updated is None:
        console.print(f"[yellow]No proposal {proposal_id} for {bot}.[/yellow]")
        return
    console.print(f"[green]Rejected {proposal_id} for {bot}.[/green]")


# --- Episodes subcommands ---


@episodes_app.command("show")
def episodes_show(
    bot: str = typer.Argument(help="Bot name"),
    since: str = typer.Option(None, "--since", help="YYYY-MM-DD lower bound (inclusive)"),
    kind: str = typer.Option(
        None,
        "--kind",
        help="Filter by episode kind (fact|event|decision|change)",
    ),
    limit: int = typer.Option(20, "--limit", "-n", help="Max rows to print"),
) -> None:
    """Print the bot's episodic timeline newest-first."""
    from rich.console import Console
    from rich.table import Table

    from abyss.config import load_bot_config
    from abyss.episodes import iter_episodes

    console = Console()
    if not load_bot_config(bot):
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)
    kinds = (kind,) if kind else None
    rows = list(iter_episodes(bot, since=since, kinds=kinds, limit=limit))
    if not rows:
        console.print(f"[yellow]No episodes for '{bot}'.[/yellow]")
        return
    table = Table(title=f"Episodes — {bot}")
    table.add_column("Date")
    table.add_column("Kind")
    table.add_column("Summary")
    table.add_column("Source")
    for row in rows:
        table.add_row(row.date, row.kind, row.summary, row.source_turn)
    console.print(table)


@episodes_app.command("extract")
def episodes_extract(
    bot: str = typer.Argument(help="Bot name"),
    date: str = typer.Option(
        None,
        "--date",
        help="YYMMDD to extract (defaults to yesterday UTC)",
    ),
) -> None:
    """Run extraction now for one day and persist episodes + facts."""
    import asyncio

    from rich.console import Console

    from abyss.config import load_bot_config
    from abyss.episodes import extract_yesterday

    console = Console()
    config = load_bot_config(bot)
    if not config:
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)
    console.print(f"[cyan]Extracting episodes for {bot} ({date or 'yesterday'})…[/cyan]")
    episode_ids, fact_ids = asyncio.run(extract_yesterday(bot, config, yymmdd=date))
    console.print(
        f"[green]Done — {len(episode_ids)} episodes, {len(fact_ids)} facts persisted.[/green]"
    )


@episodes_app.command("schedule")
def episodes_schedule(
    bot: str = typer.Argument(help="Bot name"),
    cron_expr: str = typer.Option(
        None,
        "--cron",
        "-c",
        help="Cron schedule (default: nightly 03:00)",
    ),
) -> None:
    """Register the nightly episode-extraction cron job for ``bot``."""
    from rich.console import Console

    from abyss.config import load_bot_config
    from abyss.cron import add_cron_job, get_cron_job
    from abyss.episodes import EPISODE_EXTRACT_JOB_NAME

    console = Console()
    if not load_bot_config(bot):
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)
    if get_cron_job(bot, EPISODE_EXTRACT_JOB_NAME):
        console.print(
            f"[yellow]'{EPISODE_EXTRACT_JOB_NAME}' already scheduled for {bot}. "
            "Unschedule first to change cadence.[/yellow]"
        )
        raise typer.Exit(1)
    schedule = (cron_expr or "0 3 * * *").strip()
    add_cron_job(
        bot,
        {
            "name": EPISODE_EXTRACT_JOB_NAME,
            "schedule": schedule,
            "enabled": True,
            "message": (
                "Nightly episodic memory extraction. "
                "Reads yesterday's conversation logs and updates "
                "episodes.jsonl + facts.db."
            ),
        },
    )
    console.print(
        f"[green]Scheduled '{EPISODE_EXTRACT_JOB_NAME}' for {bot} (cron='{schedule}').[/green]"
    )


@episodes_app.command("unschedule")
def episodes_unschedule(bot: str = typer.Argument(help="Bot name")) -> None:
    """Remove the nightly episode-extraction cron job for ``bot``."""
    from rich.console import Console

    from abyss.config import load_bot_config
    from abyss.cron import remove_cron_job
    from abyss.episodes import EPISODE_EXTRACT_JOB_NAME

    console = Console()
    if not load_bot_config(bot):
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)
    if remove_cron_job(bot, EPISODE_EXTRACT_JOB_NAME):
        console.print(f"[green]Removed '{EPISODE_EXTRACT_JOB_NAME}' from {bot}.[/green]")
    else:
        console.print(f"[yellow]No '{EPISODE_EXTRACT_JOB_NAME}' job to remove for {bot}.[/yellow]")


# --- Facts subcommands ---


@facts_app.command("show")
def facts_show(
    bot: str = typer.Argument(help="Bot name"),
    subject: str = typer.Option(None, "--subject", "-s", help="Filter by exact subject"),
    min_confidence: float = typer.Option(
        0.0, "--min-confidence", help="Drop rows below this confidence"
    ),
    limit: int = typer.Option(20, "--limit", "-n"),
    include_retracted: bool = typer.Option(
        False, "--include-retracted", help="Show retracted rows too"
    ),
) -> None:
    """Print the bot's structured facts ordered by confidence."""
    from rich.console import Console
    from rich.table import Table

    from abyss.config import load_bot_config
    from abyss.episodes import query_facts

    console = Console()
    if not load_bot_config(bot):
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)
    statuses: tuple[str, ...] = (
        ("active", "retracted", "superseded") if include_retracted else ("active",)
    )
    rows = query_facts(
        bot,
        subject=subject,
        min_confidence=min_confidence,
        statuses=statuses,
        limit=limit,
    )
    if not rows:
        console.print(f"[yellow]No facts for '{bot}'.[/yellow]")
        return
    table = Table(title=f"Facts — {bot}")
    table.add_column("ID")
    table.add_column("Subject")
    table.add_column("Claim")
    table.add_column("Confidence")
    table.add_column("Status")
    table.add_column("Source")
    for row in rows:
        table.add_row(
            str(row["id"]),
            row["subject"],
            row["claim"],
            f"{row['confidence']:.2f}",
            row["status"],
            row.get("source_turn", "") or "",
        )
    console.print(table)


@facts_app.command("retract")
def facts_retract(
    bot: str = typer.Argument(help="Bot name"),
    fact_id: int = typer.Argument(help="Fact id (see ``abyss facts show``)"),
) -> None:
    """Retract one fact — flips status to 'retracted' and zeros confidence."""
    from rich.console import Console

    from abyss.config import load_bot_config
    from abyss.episodes import retract_fact

    console = Console()
    if not load_bot_config(bot):
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)
    if retract_fact(bot, fact_id):
        console.print(f"[green]Retracted fact {fact_id} for {bot}.[/green]")
    else:
        console.print(f"[yellow]No fact {fact_id} to retract for {bot}.[/yellow]")


# --- About Me subcommands ---


@about_me_app.command("init")
def about_me_init() -> None:
    """Create the ABOUT_ME/ scaffold and INDEX.md (idempotent)."""
    from rich.console import Console

    from abyss.about_me import ensure_about_me_scaffold

    console = Console()
    directory = ensure_about_me_scaffold()
    console.print(f"[green]ABOUT_ME ready at {directory}[/green]")


@about_me_app.command("show")
def about_me_show(
    category: str | None = typer.Argument(
        None,
        help="Category name (omit for full dump including INDEX).",
    ),
) -> None:
    """Render ABOUT_ME contents as Markdown."""
    from rich.console import Console
    from rich.markdown import Markdown

    from abyss.about_me import (
        ABOUT_ME_CATEGORIES,
        about_me_file,
        index_file,
        load_index,
    )

    console = Console()

    if category is None:
        index_content = load_index()
        if not index_content.strip():
            console.print("[yellow]ABOUT_ME is empty. Run `abyss about-me init` first.[/yellow]")
            raise typer.Exit(0)
        console.print(Markdown(index_content))
        console.print(f"\n[dim]Index file: {index_file()}[/dim]")
        return

    if category not in ABOUT_ME_CATEGORIES:
        console.print(
            f"[red]Unknown category '{category}'. Valid: {', '.join(ABOUT_ME_CATEGORIES)}.[/red]"
        )
        raise typer.Exit(1)

    path = about_me_file(category)
    if not path.exists():
        console.print(f"[yellow]No data for '{category}'. Run `abyss about-me init`.[/yellow]")
        raise typer.Exit(0)
    console.print(Markdown(path.read_text(encoding="utf-8")))
    console.print(f"\n[dim]File: {path}[/dim]")


@about_me_app.command("list")
def about_me_list() -> None:
    """List every entry key across categories in a table."""
    from rich.console import Console
    from rich.table import Table

    from abyss.about_me import ABOUT_ME_CATEGORIES, list_entries

    console = Console()
    grouped = list_entries()

    table = Table(show_header=True, header_style="bold")
    table.add_column("Category")
    table.add_column("Key")
    table.add_column("Value")
    table.add_column("Status")
    table.add_column("Confirmed")

    total = 0
    for category in ABOUT_ME_CATEGORIES:
        for entry in grouped.get(category, []):
            value = entry.value
            if len(value) > 50:
                value = value[:47] + "..."
            table.add_row(
                category,
                entry.key,
                value,
                entry.status,
                entry.last_confirmed or "-",
            )
            total += 1

    if total == 0:
        console.print(
            "[yellow]No ABOUT_ME entries yet. Run `abyss about-me init` to scaffold.[/yellow]"
        )
        return
    console.print(table)
    console.print(f"\n[dim]Total: {total} entries.[/dim]")


@about_me_app.command("migrate")
def about_me_migrate(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Classify GLOBAL_MEMORY.md without writing ABOUT_ME files.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt.",
    ),
    model: str = typer.Option(
        "haiku",
        "--model",
        help="Claude model for classification (default haiku).",
    ),
) -> None:
    """Classify GLOBAL_MEMORY.md into ABOUT_ME category files."""
    import asyncio
    import json

    from rich.console import Console

    from abyss.about_me import migrate_from_global_memory

    console = Console()

    if not dry_run and not yes:
        confirm = typer.confirm(
            "GLOBAL_MEMORY.md will be classified and written into ABOUT_ME/. Proceed?",
            default=False,
        )
        if not confirm:
            console.print("[yellow]Migration cancelled.[/yellow]")
            raise typer.Exit(0)

    try:
        result = asyncio.run(migrate_from_global_memory(dry_run=dry_run, model=model))
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    if dry_run:
        console.print("[bold]Dry-run classification:[/bold]")
        console.print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    counts = {category: len(items) for category, items in result.items()}
    total = sum(counts.values())
    console.print(f"[green]Migrated {total} entries.[/green]")
    for category, count in counts.items():
        if count:
            console.print(f"  - {category}: {count}")
    console.print(
        "\n[dim]GLOBAL_MEMORY.md was left intact — clear it manually if you "
        "no longer want both sources injected.[/dim]"
    )


@about_me_app.command("edit")
def about_me_edit(
    category: str = typer.Argument(help="Category to edit."),
) -> None:
    """Open a category file in $EDITOR and rebuild INDEX on save."""
    import os
    import subprocess

    from rich.console import Console

    from abyss.about_me import (
        ABOUT_ME_CATEGORIES,
        about_me_file,
        ensure_about_me_scaffold,
        rebuild_index,
    )

    console = Console()

    if category not in ABOUT_ME_CATEGORIES:
        console.print(
            f"[red]Unknown category '{category}'. Valid: {', '.join(ABOUT_ME_CATEGORIES)}.[/red]"
        )
        raise typer.Exit(1)

    ensure_about_me_scaffold()
    path = about_me_file(category)
    editor = os.environ.get("EDITOR", "vi")
    subprocess.run([editor, str(path)])
    rebuild_index()
    console.print(f"[green]INDEX rebuilt after editing {path}.[/green]")


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
    """Run heartbeat immediately (for testing).

    Calls ``execute_heartbeat`` — the same function the scheduler
    invokes — so a run that produces real signal (no ``HEARTBEAT_OK``
    marker) hits ``conversation-*.md`` + Web Push the same way a
    scheduled heartbeat does.
    """
    import asyncio

    from rich.console import Console

    from abyss.config import load_bot_config
    from abyss.heartbeat import execute_heartbeat, load_heartbeat_markdown

    console = Console()

    bot_config = load_bot_config(bot)
    if not bot_config:
        console.print(f"[red]Bot '{bot}' not found.[/red]")
        raise typer.Exit(1)

    if not load_heartbeat_markdown(bot):
        console.print(
            f"[yellow]No HEARTBEAT.md found. Run 'abyss heartbeat enable {bot}' first.[/yellow]"
        )
        raise typer.Exit(1)

    console.print(f"[cyan]Running heartbeat for '{bot}'...[/cyan]")
    try:
        asyncio.run(execute_heartbeat(bot_name=bot, bot_config=bot_config))
    except Exception as error:
        console.print(f"[red]Error: {error}[/red]")
        raise typer.Exit(1) from error
    console.print(
        "\n[green]Done.[/green] Result lands in the mobile Routines tab "
        "and the bot's ``heartbeat_sessions/conversation-*.md`` file."
    )


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
