"""Onboarding and environment checking for cclaw."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from dataclasses import dataclass

import typer
from rich.console import Console
from rich.panel import Panel

from cclaw.config import (
    add_bot_to_config,
    bot_directory,
    bot_exists,
    cclaw_home,
    default_config,
    detect_local_timezone,
    load_bot_config,
    load_config,
    save_bot_config,
    save_config,
)

console = Console()

MAXIMUM_TOKEN_RETRY = 3


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
            "  Then run again: cclaw init",
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


def run_environment_checks() -> list[EnvironmentCheckResult]:
    """Run all environment checks and return results."""
    return [check_python(), check_node(), check_claude_code()]


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


async def validate_telegram_token(token: str) -> dict | None:
    """Validate a Telegram bot token. Returns bot info dict or None."""
    from telegram import Bot

    try:
        bot = Bot(token=token)
        bot_info = await bot.get_me()
        return {
            "username": f"@{bot_info.username}",
            "botname": bot_info.first_name,
        }
    except Exception:
        return None


def prompt_telegram_token() -> tuple[str, dict]:
    """Prompt user for Telegram bot token with retry. Returns (token, bot_info)."""
    from cclaw.utils import prompt_input

    console.print("\n[bold]Connecting Telegram bot.[/bold]")
    console.print()
    console.print("  1. Send a DM to @BotFather on Telegram.")
    console.print("  2. Create a bot with the /newbot command.")
    console.print("  3. Enter the issued token below.")
    console.print()

    for attempt in range(MAXIMUM_TOKEN_RETRY):
        token = prompt_input("Bot Token:")
        console.print("Verifying token...")

        bot_info = asyncio.run(validate_telegram_token(token))
        if bot_info:
            console.print(
                f"[green]OK[/green] Bot verified: {bot_info['username']} ({bot_info['botname']})"
            )
            return token, bot_info

        remaining = MAXIMUM_TOKEN_RETRY - attempt - 1
        if remaining > 0:
            console.print(f"[red]Invalid token. {remaining} attempts remaining.[/red]")
        else:
            console.print("[red]Maximum retry attempts exceeded.[/red]")
            raise typer.Exit(1)

    raise typer.Exit(1)


def prompt_bot_profile() -> dict:
    """Prompt user for bot profile information. Returns profile dict."""
    from cclaw.utils import prompt_input, prompt_multiline

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

    from cclaw.utils import prompt_input

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
    from cclaw.utils import prompt_input

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
    """Check if cclaw daemon is currently running."""
    from cclaw.bot_manager import _plist_path

    return _plist_path().exists()


def _restart_daemon() -> None:
    """Restart the cclaw daemon to pick up new bot."""
    from cclaw.bot_manager import start_bots, stop_bots

    console.print("\n[yellow]Restarting daemon to register new bot...[/yellow]")
    try:
        stop_bots()
        start_bots(daemon=True)
    except Exception as error:
        console.print(f"[red]Failed to restart daemon: {error}[/red]")
        console.print("  Restart manually: [bold]cclaw stop && cclaw start --daemon[/bold]")


def create_bot(token: str, bot_info: dict, profile: dict) -> None:
    """Create bot configuration files."""
    bot_config = {
        "telegram_token": token,
        "telegram_username": bot_info["username"],
        "telegram_botname": bot_info["botname"],
        "display_name": profile.get("display_name", ""),
        "personality": profile["personality"],
        "role": profile["role"],
        "goal": profile.get("goal", ""),
        "allowed_users": [],
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

    save_bot_config(profile["name"], bot_config)
    add_bot_to_config(profile["name"])

    home = cclaw_home()
    console.print()
    console.print(
        Panel(
            f"[green]OK[/green] {profile['name']} created!\n\n"
            f"  Name:      {profile.get('display_name') or profile['name']}\n"
            f"  Personality: {profile['personality']}\n"
            f"  Role:      {profile['role']}\n"
            f"  Goal:      {profile.get('goal', '')}\n"
            f"  Path:      {home / 'bots' / profile['name']}\n"
            f"  Telegram:  {bot_info['username']}",
            title=profile["name"],
        )
    )

    if _is_daemon_running():
        _restart_daemon()
    else:
        console.print("\n  Start the bot: [bold]cclaw start[/bold]")


def run_onboarding() -> None:
    """Run the full onboarding flow (environment check + timezone)."""
    console.print("[bold]Starting cclaw initial setup.[/bold]")

    checks = run_environment_checks()
    if not display_environment_checks(checks):
        raise typer.Exit(1)

    console.print("\n[green]Environment check passed![/green]")

    timezone_name = prompt_timezone()
    language = prompt_language()
    save_init_config(timezone_name, language)

    console.print()
    console.print("[green]Initial setup complete![/green]")
    console.print("\n  Next step: [bold]cclaw bot add[/bold] to create your first bot.")


def add_bot() -> None:
    """Add a new bot (reuses onboarding Steps 2+3)."""
    token, bot_info = prompt_telegram_token()
    profile = prompt_bot_profile()
    create_bot(token, bot_info, profile)


def _display_bridge_status() -> None:
    """Display bridge process and connection status."""
    from cclaw.bridge import _bridge_log_path, _socket_path, is_bridge_running

    # Process status
    if is_bridge_running():
        console.print("  [green]OK[/green] Bridge process running")
    else:
        console.print("  [yellow]--[/yellow] Bridge process not running (starts with cclaw start)")

    # Socket status
    from pathlib import Path

    socket = Path(_socket_path())
    if socket.exists():
        health = asyncio.run(_check_bridge_health())
        if health:
            console.print(f"  [green]OK[/green] Bridge socket reachable ({_socket_path()})")
        else:
            console.print(
                f"  [red]FAIL[/red] Bridge socket exists but not responding ({_socket_path()})"
            )
    else:
        console.print(f"  [yellow]--[/yellow] Bridge socket not found ({_socket_path()})")

    # Log file
    log_path = Path(_bridge_log_path())
    if log_path.exists():
        size_kilobytes = log_path.stat().st_size / 1024
        console.print(f"  [green]OK[/green] Bridge log: {log_path} ({size_kilobytes:.0f}KB)")
    else:
        console.print("  [yellow]--[/yellow] Bridge log not found")

    # SDK check
    bridge_directory = Path(_socket_path()).parent  # fallback
    from cclaw.bridge import _bridge_directory

    try:
        bridge_directory = _bridge_directory()
        package_json = (
            bridge_directory
            / "node_modules"
            / "@anthropic-ai"
            / "claude-agent-sdk"
            / "package.json"
        )
        if package_json.exists():
            import json

            sdk_info = json.loads(package_json.read_text())
            console.print(f"  [green]OK[/green] Claude Agent SDK v{sdk_info.get('version', '?')}")
        else:
            console.print(
                "  [yellow]--[/yellow] Claude Agent SDK not installed (run cclaw start to install)"
            )
    except Exception:
        console.print("  [yellow]--[/yellow] Bridge directory not initialized")


async def _check_bridge_health() -> bool:
    """Try to connect to bridge and check health."""
    try:
        from cclaw.bridge import bridge_health

        result = await bridge_health()
        return result is not None
    except Exception:
        return False


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
    from cclaw.bot_manager import _qmd_health_check

    daemon_running = asyncio.run(_qmd_health_check())
    if daemon_running:
        console.print("  [green]OK[/green] QMD daemon: running (port 8181)")
    else:
        console.print("  [yellow]--[/yellow] QMD daemon: not running (starts with cclaw start)")


def run_doctor() -> None:
    """Run environment and configuration diagnostics."""
    console.print("[bold]cclaw doctor[/bold]\n")

    checks = run_environment_checks()
    display_environment_checks(checks)

    console.print()

    config = load_config()
    if config is None:
        console.print("[yellow]No config.yaml found. Run 'cclaw init' first.[/yellow]")
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

        token = bot_config.get("telegram_token", "")
        bot_info = asyncio.run(validate_telegram_token(token))
        if bot_info:
            console.print(f"  [green]OK[/green] {name}: token valid ({bot_info['username']})")
        else:
            console.print(f"  [red]FAIL[/red] {name}: token invalid")

        session_directory = bot_directory(name) / "sessions"
        if session_directory.exists():
            session_count = len(list(session_directory.iterdir()))
            console.print(f"       Sessions: {session_count}")
        else:
            console.print("       Sessions: 0")

    # Bridge status
    console.print("\n[bold]Bridge:[/bold]")
    _display_bridge_status()

    # QMD status
    console.print("\n[bold]QMD:[/bold]")
    _display_qmd_status()
