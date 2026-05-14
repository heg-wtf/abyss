"""Onboarding and environment checking for abyss."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from dataclasses import dataclass

import typer
from rich.console import Console
from rich.panel import Panel

from abyss.config import (
    abyss_home,
    add_bot_to_config,
    bot_directory,
    bot_exists,
    default_config,
    detect_local_timezone,
    load_bot_config,
    load_config,
    save_bot_config,
    save_config,
)

console = Console()


@dataclass
class EnvironmentCheckResult:
    """Result of an environment check."""

    name: str
    available: bool
    version: str
    message: str


def check_claude_code() -> EnvironmentCheckResult:
    """Check if Claude Code CLI is installed."""
    path = shutil.which("claude")
    if not path:
        return EnvironmentCheckResult(
            name="Claude Code",
            available=False,
            version="",
            message="Claude Code is not installed.\n\n"
            "  Install:\n"
            "    npm install -g @anthropic-ai/claude-code\n\n"
            "  Then run again: abyss init",
        )
    try:
        result = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=10)
        version = result.stdout.strip() or result.stderr.strip()
    except (subprocess.TimeoutExpired, OSError):
        version = "unknown"

    return EnvironmentCheckResult(name="Claude Code", available=True, version=version, message="")


def check_node() -> EnvironmentCheckResult:
    """Check if Node.js is installed."""
    path = shutil.which("node")
    if not path:
        return EnvironmentCheckResult(
            name="Node.js",
            available=False,
            version="",
            message="Node.js is not installed. Required for Claude Code.",
        )
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=10)
        version = result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        version = "unknown"

    return EnvironmentCheckResult(name="Node.js", available=True, version=version, message="")


def check_python() -> EnvironmentCheckResult:
    """Check Python version."""
    import sys

    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    return EnvironmentCheckResult(name="Python", available=True, version=version, message="")


def check_sqlite_fts5() -> EnvironmentCheckResult:
    """Verify the bundled SQLite supports FTS5 — needed for conversation search."""
    import sqlite3

    from abyss.conversation_index import is_fts5_available

    available = is_fts5_available()
    if not available:
        return EnvironmentCheckResult(
            name="SQLite FTS5",
            available=False,
            version=sqlite3.sqlite_version,
            message=(
                "SQLite FTS5 extension is not compiled into this Python's "
                "sqlite3 module. Conversation search will be disabled."
            ),
        )
    return EnvironmentCheckResult(
        name="SQLite FTS5",
        available=True,
        version=sqlite3.sqlite_version,
        message="",
    )


def run_environment_checks() -> list[EnvironmentCheckResult]:
    """Run all environment checks and return results."""
    return [check_python(), check_node(), check_claude_code(), check_sqlite_fts5()]


def display_environment_checks(checks: list[EnvironmentCheckResult]) -> bool:
    """Display environment check results. Returns True if all passed."""
    console.print("\nChecking environment...")
    all_passed = True
    for check in checks:
        if check.available:
            console.print(f"  [green]OK[/green] {check.name} {check.version}")
        else:
            console.print(f"  [red]FAIL[/red] {check.name}")
            if check.message:
                console.print(f"\n  {check.message}")
            all_passed = False
    return all_passed


def prompt_bot_profile() -> dict:
    """Prompt user for bot profile information. Returns profile dict."""
    from abyss.utils import prompt_input, prompt_multiline

    console.print("\n[bold]Setting up bot profile.[/bold]\n")

    while True:
        name = prompt_input("Bot name (English, used as directory name):")
        name = name.strip().lower().replace(" ", "-")
        if not name.isascii() or not name.replace("-", "").isalnum():
            console.print("[red]Use only English letters, numbers, and hyphens.[/red]")
            continue
        if bot_exists(name):
            console.print(f"[red]Bot '{name}' already exists.[/red]")
            continue
        break

    display_name = prompt_input("Display name (what you call this bot):")
    personality = prompt_multiline("Bot personality:")
    role = prompt_multiline("Bot role (what it does):")
    goal = prompt_multiline("Bot goal (why it exists):")

    return {
        "name": name,
        "display_name": display_name.strip(),
        "personality": personality,
        "role": role,
        "goal": goal,
    }


def prompt_timezone() -> str:
    """Prompt user for timezone selection. Returns IANA timezone string."""
    from zoneinfo import ZoneInfo

    from abyss.utils import prompt_input

    detected = detect_local_timezone()

    console.print("\n[bold]Setting timezone.[/bold]\n")
    console.print(f"  Detected local timezone: [cyan]{detected}[/cyan]")
    console.print()

    timezone_input = prompt_input(f"Timezone (e.g. Asia/Seoul, America/New_York) [{detected}]:")
    timezone_input = timezone_input.strip()

    if not timezone_input:
        timezone_input = detected

    try:
        ZoneInfo(timezone_input)
    except (KeyError, ValueError):
        console.print(f"[red]Invalid timezone: {timezone_input}. Using {detected}.[/red]")
        timezone_input = detected

    console.print(f"  [green]OK[/green] Timezone: {timezone_input}")
    return timezone_input


SUPPORTED_LANGUAGES = [
    "Korean",
    "English",
    "Japanese",
    "Chinese",
    "Spanish",
    "French",
    "German",
    "Portuguese",
    "Vietnamese",
    "Thai",
]


def prompt_language() -> str:
    """Prompt user for language selection. Returns language name string."""
    from abyss.utils import prompt_input

    console.print("\n[bold]Setting response language.[/bold]\n")
    for index, language in enumerate(SUPPORTED_LANGUAGES, 1):
        console.print(f"  {index}. {language}")
    console.print()

    selection = prompt_input(f"Select language (1-{len(SUPPORTED_LANGUAGES)}) [1]:")
    selection = selection.strip()

    if not selection:
        selected = SUPPORTED_LANGUAGES[0]
    else:
        try:
            number = int(selection)
            if 1 <= number <= len(SUPPORTED_LANGUAGES):
                selected = SUPPORTED_LANGUAGES[number - 1]
            else:
                console.print(f"[red]Invalid selection. Using {SUPPORTED_LANGUAGES[0]}.[/red]")
                selected = SUPPORTED_LANGUAGES[0]
        except ValueError:
            console.print(f"[red]Invalid input. Using {SUPPORTED_LANGUAGES[0]}.[/red]")
            selected = SUPPORTED_LANGUAGES[0]

    console.print(f"  [green]OK[/green] Language: {selected}")
    return selected


def save_init_config(timezone_name: str, language: str) -> None:
    """Save timezone and language to config.yaml."""
    config = load_config() or default_config()
    config["timezone"] = timezone_name
    config["language"] = language
    save_config(config)


def _is_daemon_running() -> bool:
    """Check if abyss daemon is currently running."""
    from abyss.bot_manager import _plist_path

    return _plist_path().exists()


def _restart_daemon() -> None:
    """Restart the abyss daemon to pick up new bot."""
    from abyss.bot_manager import start_bots, stop_bots

    console.print("\n[yellow]Restarting daemon to register new bot...[/yellow]")
    try:
        stop_bots()
        start_bots(daemon=True)
    except Exception as error:
        console.print(f"[red]Failed to restart daemon: {error}[/red]")
        console.print("  Restart manually: [bold]abyss stop && abyss start --daemon[/bold]")


def prompt_backend_choice() -> dict | None:
    """Backend prompt retired in v2026.05.15.

    abyss is Claude Code only — kept as a no-op so callers don't have to
    branch. Returns ``None`` so ``create_bot`` omits the ``backend:``
    block from ``bot.yaml``.
    """
    return None


def create_bot(
    profile: dict,
    backend_block: dict | None = None,
) -> None:
    """Create bot configuration files.

    Telegram fields are gone from ``bot.yaml`` — the dashboard chat
    + mobile PWA are now the only inbox/outbox. ``allowed_users``
    used to gate Telegram messaging; access is now enforced at the
    network layer (Tailscale / loopback origin on the dashboard).
    """
    bot_config: dict = {
        "display_name": profile.get("display_name", ""),
        "personality": profile["personality"],
        "role": profile["role"],
        "goal": profile.get("goal", ""),
        "claude_args": [],
        "streaming": False,
        "heartbeat": {
            "enabled": False,
            "interval_minutes": 30,
            "active_hours": {
                "start": "07:00",
                "end": "23:00",
            },
        },
    }
    if backend_block is not None:
        bot_config["backend"] = backend_block

    save_bot_config(profile["name"], bot_config)
    add_bot_to_config(profile["name"])

    home = abyss_home()
    console.print()
    console.print(
        Panel(
            f"[green]OK[/green] {profile['name']} created!\n\n"
            f"  Name:      {profile.get('display_name') or profile['name']}\n"
            f"  Personality: {profile['personality']}\n"
            f"  Role:      {profile['role']}\n"
            f"  Goal:      {profile.get('goal', '')}\n"
            f"  Path:      {home / 'bots' / profile['name']}",
            title=profile["name"],
        )
    )

    if _is_daemon_running():
        _restart_daemon()
    else:
        console.print("\n  Start the bot: [bold]abyss start[/bold]")


def run_onboarding() -> None:
    """Run the full onboarding flow (environment check + timezone)."""
    console.print("[bold]Starting abyss initial setup.[/bold]")

    checks = run_environment_checks()
    if not display_environment_checks(checks):
        raise typer.Exit(1)

    console.print("\n[green]Environment check passed![/green]")

    timezone_name = prompt_timezone()
    language = prompt_language()
    save_init_config(timezone_name, language)

    console.print()
    console.print("[green]Initial setup complete![/green]")
    console.print("\n  Next step: [bold]abyss bot add[/bold] to create your first bot.")


def add_bot() -> None:
    """Add a new bot — profile + backend, no Telegram token required."""
    profile = prompt_bot_profile()
    backend_block = prompt_backend_choice()
    create_bot(profile, backend_block=backend_block)


def _display_sdk_status() -> None:
    """Display Python Agent SDK availability status."""
    from abyss.sdk_client import is_sdk_available

    if is_sdk_available():
        try:
            import claude_agent_sdk

            version = getattr(claude_agent_sdk, "__version__", "unknown")
            console.print(f"  [green]OK[/green] Python Agent SDK v{version}")
        except Exception:
            console.print("  [green]OK[/green] Python Agent SDK available")
    else:
        console.print(
            "  [yellow]--[/yellow] Python Agent SDK not installed (pip install claude-agent-sdk)"
        )


def _display_qmd_status() -> None:
    """Display QMD CLI and daemon status."""
    qmd_path = shutil.which("qmd")
    if not qmd_path:
        console.print("  [yellow]--[/yellow] QMD not installed (npm install -g @tobilu/qmd)")
        return

    try:
        result = subprocess.run(
            ["qmd", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            import json

            status = json.loads(result.stdout)
            documents = status.get("totalDocuments", 0)
            collections = status.get("collections", [])
            has_vector = status.get("hasVectorIndex", False)
            console.print(f"  [green]OK[/green] QMD CLI: {qmd_path}")
            console.print(f"       Collections: {len(collections)}")
            console.print(f"       Documents: {documents}")
            console.print(f"       Vector index: {'yes' if has_vector else 'no'}")
        else:
            # Fallback: non-JSON status
            console.print(f"  [green]OK[/green] QMD CLI: {qmd_path}")
    except (subprocess.TimeoutExpired, OSError, ValueError):
        console.print(f"  [green]OK[/green] QMD CLI: {qmd_path}")

    # Daemon status
    from abyss.bot_manager import _qmd_health_check

    daemon_running = asyncio.run(_qmd_health_check())
    if daemon_running:
        console.print("  [green]OK[/green] QMD daemon: running (port 8181)")
    else:
        console.print("  [yellow]--[/yellow] QMD daemon: not running (starts with abyss start)")


def run_doctor() -> None:
    """Run environment and configuration diagnostics."""
    console.print("[bold]abyss doctor[/bold]\n")

    checks = run_environment_checks()
    display_environment_checks(checks)

    console.print()

    config = load_config()
    if config is None:
        console.print("[yellow]No config.yaml found. Run 'abyss init' first.[/yellow]")
        return

    console.print("[green]OK[/green] config.yaml found")
    console.print(f"  Timezone: {config.get('timezone', 'UTC')}")
    console.print(f"  Language: {config.get('language', 'Korean')}")
    console.print(f"  Log level: {config.get('settings', {}).get('log_level', 'N/A')}")

    bots = config.get("bots", [])
    if not bots:
        console.print("[yellow]No bots configured.[/yellow]")
        return

    console.print(f"\n[bold]Bots ({len(bots)}):[/bold]")

    for bot_entry in bots:
        name = bot_entry["name"]
        bot_config = load_bot_config(name)
        if not bot_config:
            console.print(f"  [red]FAIL[/red] {name}: bot.yaml missing")
            continue

        display_name = bot_config.get("display_name") or name
        console.print(f"  [green]OK[/green] {name}: {display_name}")

        session_directory = bot_directory(name) / "sessions"
        if session_directory.exists():
            session_count = len(list(session_directory.iterdir()))
            console.print(f"       Sessions: {session_count}")
        else:
            console.print("       Sessions: 0")

    # SDK status
    console.print("\n[bold]SDK:[/bold]")
    _display_sdk_status()

    # QMD status
    console.print("\n[bold]QMD:[/bold]")
    _display_qmd_status()

    # Group surface was removed alongside Telegram; a fresh PWA-
    # native multi-bot room model will land in a separate PR.
