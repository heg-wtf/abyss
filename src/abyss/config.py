"""Configuration management for abyss."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml


def abyss_home() -> Path:
    """Return the abyss home directory. Defaults to ~/.abyss/, overridable via ABYSS_HOME."""
    return Path(os.environ.get("ABYSS_HOME", Path.home() / ".abyss"))


def ensure_home() -> Path:
    """Ensure the abyss home directory exists and return its path."""
    home = abyss_home()
    home.mkdir(parents=True, exist_ok=True)
    return home


def config_path() -> Path:
    """Return path to the global config.yaml."""
    return abyss_home() / "config.yaml"


def load_config() -> dict[str, Any] | None:
    """Load the global config.yaml. Returns None if it doesn't exist."""
    path = config_path()
    if not path.exists():
        return None
    with open(path) as file:
        return yaml.safe_load(file)


def save_config(config: dict[str, Any]) -> None:
    """Save the global config.yaml."""
    ensure_home()
    with open(config_path(), "w") as file:
        yaml.dump(config, file, default_flow_style=False, allow_unicode=True)


def bot_directory(name: str) -> Path:
    """Return the bot directory path."""
    return abyss_home() / "bots" / name


def load_bot_config(name: str) -> dict[str, Any] | None:
    """Load a bot's bot.yaml. Returns None if it doesn't exist."""
    path = bot_directory(name) / "bot.yaml"
    if not path.exists():
        return None
    with open(path) as file:
        return yaml.safe_load(file)


def save_bot_config(name: str, bot_config: dict[str, Any]) -> None:
    """Save a bot's bot.yaml and generate CLAUDE.md."""
    directory = bot_directory(name)
    directory.mkdir(parents=True, exist_ok=True)

    sessions_directory = directory / "sessions"
    sessions_directory.mkdir(exist_ok=True)

    with open(directory / "bot.yaml", "w") as file:
        yaml.dump(bot_config, file, default_flow_style=False, allow_unicode=True)

    # Lazy import to avoid circular dependency with skill module
    from abyss.skill import compose_claude_md

    claude_md_content = compose_claude_md(
        bot_name=name,
        personality=bot_config.get("personality", ""),
        role=bot_config.get("role", bot_config.get("description", "")),
        goal=bot_config.get("goal", ""),
        skill_names=bot_config.get("skills", []),
        bot_path=directory,
    )
    with open(directory / "CLAUDE.md", "w") as file:
        file.write(claude_md_content)


def generate_claude_md(name: str, personality: str, role: str, goal: str = "") -> str:
    """Generate CLAUDE.md content for a bot."""
    language = get_language()
    sections = f"""# {name}

## Personality
{personality}

## Role
{role}
"""
    if goal:
        sections += f"""
## Goal
{goal}
"""

    sections += f"""
## Rules
- Respond in {language}.
- Save generated files to the workspace/ directory.
- Always ask for confirmation before executing dangerous commands (delete, restart, etc.).
"""
    return sections


def default_config() -> dict[str, Any]:
    """Return a default config structure."""
    return {
        "bots": [],
        "timezone": "UTC",
        "language": "Korean",
        "settings": {
            "log_level": "INFO",
            "command_timeout": 300,
        },
        "claude_code": default_claude_code_config(),
    }


def default_claude_code_config() -> dict[str, bool]:
    """Default toggles for Claude Code env injection.

    Each ``*_env`` key maps to an environment variable injected into
    ``claude -p`` subprocess and the Python Agent SDK. ``mcp_always_load``
    flips on the ``alwaysLoad`` flag for abyss auto-injected MCP servers
    (qmd, conversation_search) so the host preconnects them at startup
    instead of lazily on first call.

    Users can disable any toggle by setting the value to ``false`` in
    ``config.yaml``.
    """
    return {
        "prompt_caching_1h": True,
        "fork_subagent": True,
        "mcp_nonblocking": True,
        "hide_cwd": True,
        "mcp_always_load": True,
    }


# Map config toggle name -> (env var name, env value when enabled)
CLAUDE_CODE_ENV_TOGGLES: dict[str, tuple[str, str]] = {
    "prompt_caching_1h": ("ENABLE_PROMPT_CACHING_1H", "1"),
    "fork_subagent": ("CLAUDE_CODE_FORK_SUBAGENT", "1"),
    "mcp_nonblocking": ("MCP_CONNECTION_NONBLOCKING", "true"),
    "hide_cwd": ("CLAUDE_CODE_HIDE_CWD", "1"),
}

# Always-on env vars (cannot be disabled).
CLAUDE_CODE_ENV_ALWAYS: dict[str, str] = {
    "AI_AGENT": "abyss",
}


def get_claude_code_env() -> dict[str, str]:
    """Return Claude Code env vars to inject into subprocess and SDK calls.

    Reads the ``claude_code`` section of ``config.yaml`` and returns the
    enabled env vars merged with always-on entries (``AI_AGENT``).

    Missing or invalid config falls back to defaults (all toggles on).
    """
    config = load_config() or {}
    raw = config.get("claude_code")
    if not isinstance(raw, dict):
        raw = default_claude_code_config()

    env: dict[str, str] = dict(CLAUDE_CODE_ENV_ALWAYS)
    for toggle, (var_name, value) in CLAUDE_CODE_ENV_TOGGLES.items():
        if raw.get(toggle, True):
            env[var_name] = value
    return env


def is_mcp_always_load_enabled() -> bool:
    """Return whether abyss auto-injected MCP servers should set ``alwaysLoad``.

    Reads the ``claude_code.mcp_always_load`` toggle. Default ``True``.
    Set ``false`` in ``config.yaml`` to revert to lazy MCP connection.
    """
    config = load_config() or {}
    raw = config.get("claude_code")
    if not isinstance(raw, dict):
        return True
    return bool(raw.get("mcp_always_load", True))


# Defaults for ``sandbox.network.deniedDomains`` (Phase 5 / Claude Code 2.1.113).
# Cloud-metadata service hostnames — these are the canonical SSRF targets and
# should be unreachable from any abyss bot subprocess by default. Users can
# extend the list per-bot via ``bot.yaml.sandbox.denied_domains``.
DEFAULT_SANDBOX_DENIED_DOMAINS: tuple[str, ...] = (
    "metadata.google.internal",
    "metadata.goog",
    "169.254.169.254",
    "instance-data",
    "metadata.azure.com",
    "metadata.tencentyun.com",
    "metadata.ali",
)


def default_sandbox_denied_domains() -> list[str]:
    """Return abyss's baseline list of blocked outbound domains.

    The list is the union of cloud-metadata endpoints across major
    providers (GCP / AWS / Azure / Tencent / Aliyun). Returned as a list
    copy so callers can mutate freely.
    """
    return list(DEFAULT_SANDBOX_DENIED_DOMAINS)


def compose_bot_sandbox(bot_config: dict[str, Any] | None) -> dict[str, Any]:
    """Build the ``sandbox`` settings.json subtree for a bot.

    Reads ``bot.yaml.sandbox.denied_domains`` (or the camelCase alias
    ``deniedDomains``) and merges it on top of the default list. Order
    is preserved; duplicates are removed.
    """
    domains: list[str] = list(DEFAULT_SANDBOX_DENIED_DOMAINS)
    if isinstance(bot_config, dict):
        sandbox = bot_config.get("sandbox")
        if isinstance(sandbox, dict):
            extras = sandbox.get("denied_domains") or sandbox.get("deniedDomains") or []
            if isinstance(extras, list):
                for entry in extras:
                    if isinstance(entry, str) and entry and entry not in domains:
                        domains.append(entry)

    return {"network": {"deniedDomains": domains}}


def apply_claude_code_env(base: dict[str, str]) -> dict[str, str]:
    """Return ``base`` env merged with Claude Code toggles.

    Enabled toggles overwrite the corresponding key in ``base`` with the
    abyss-controlled value. Disabled toggles **remove** the key from
    ``base`` so that a stray host-shell export (e.g. ``ENABLE_PROMPT_CACHING_1H=1``
    in ``~/.zshrc``) cannot resurrect the feature after the user has turned
    it off in ``config.yaml``. Always-on entries are always set.

    The input dict is not mutated.
    """
    config = load_config() or {}
    raw = config.get("claude_code")
    if not isinstance(raw, dict):
        raw = default_claude_code_config()

    result = dict(base)
    for toggle, (var_name, value) in CLAUDE_CODE_ENV_TOGGLES.items():
        if raw.get(toggle, True):
            result[var_name] = value
        else:
            result.pop(var_name, None)
    for var_name, value in CLAUDE_CODE_ENV_ALWAYS.items():
        result[var_name] = value
    return result


def add_bot_to_config(name: str) -> None:
    """Add a bot entry to the global config."""
    config = load_config() or default_config()
    if "bots" not in config:
        config["bots"] = []

    existing = [b for b in config["bots"] if b["name"] == name]
    if not existing:
        config["bots"].append({"name": name, "path": str(bot_directory(name))})

    save_config(config)


def remove_bot_from_config(name: str) -> None:
    """Remove a bot entry from the global config."""
    config = load_config()
    if not config or "bots" not in config:
        return
    config["bots"] = [b for b in config["bots"] if b["name"] != name]
    save_config(config)


def load_cron_config(name: str) -> dict[str, Any]:
    """Load a bot's cron.yaml. Returns empty config if not found."""
    path = bot_directory(name) / "cron.yaml"
    if not path.exists():
        return {"jobs": []}
    with open(path) as file:
        data = yaml.safe_load(file)
    if not data or "jobs" not in data:
        return {"jobs": []}
    return data


def save_cron_config(name: str, config: dict[str, Any]) -> None:
    """Save a bot's cron.yaml."""
    path = bot_directory(name) / "cron.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as file:
        yaml.dump(config, file, default_flow_style=False, allow_unicode=True)


def cron_session_directory(bot_name: str, job_name: str) -> Path:
    """Return the cron session directory path for a job."""
    return bot_directory(bot_name) / "cron_sessions" / job_name


VALID_MODELS = ["sonnet", "opus", "haiku"]
MODEL_VERSIONS: dict[str, str] = {
    "sonnet": "4.5",
    "opus": "4.6",
    "haiku": "3.5",
}
DEFAULT_MODEL = "sonnet"
DEFAULT_STREAMING = True


def is_valid_model(model: str) -> bool:
    """Check if the model name is valid."""
    return model in VALID_MODELS


def model_display_name(model: str) -> str:
    """Return model name with version (e.g. 'opus 4.6')."""
    version = MODEL_VERSIONS.get(model, "")
    return f"{model} {version}" if version else model


def bot_exists(name: str) -> bool:
    """Check if a bot with this name already exists."""
    config = load_config()
    if not config or "bots" not in config:
        return False
    return any(b["name"] == name for b in config["bots"])


# --- Timezone ---

TIMEZONE_ABBREVIATION_MAP: dict[str, str] = {
    "KST": "Asia/Seoul",
    "JST": "Asia/Tokyo",
    "CST": "America/Chicago",
    "EST": "America/New_York",
    "PST": "America/Los_Angeles",
    "CET": "Europe/Berlin",
    "GMT": "Europe/London",
    "MST": "America/Denver",
    "HST": "Pacific/Honolulu",
    "AKST": "America/Anchorage",
    "IST": "Asia/Kolkata",
    "AEST": "Australia/Sydney",
    "NZST": "Pacific/Auckland",
}


def detect_local_timezone() -> str:
    """Detect the local system timezone as an IANA name.

    Returns an IANA timezone string (e.g., 'Asia/Seoul').
    Falls back to 'UTC' if detection fails.
    """
    local_abbreviation = time.tzname[0]
    if local_abbreviation in TIMEZONE_ABBREVIATION_MAP:
        return TIMEZONE_ABBREVIATION_MAP[local_abbreviation]

    # Try reading /etc/localtime symlink (macOS/Linux)
    try:
        import os

        localtime = os.readlink("/etc/localtime")
        # e.g., /var/db/timezone/zoneinfo/Asia/Seoul
        if "zoneinfo/" in localtime:
            candidate = localtime.split("zoneinfo/", 1)[1]
            ZoneInfo(candidate)  # validate
            return candidate
    except (OSError, KeyError, ValueError):
        pass

    return "UTC"


def get_timezone() -> str:
    """Return the timezone from config.yaml.

    This is the single source of truth for timezone across all of abyss.
    Falls back to 'UTC' if config is not found or timezone is not set.
    """
    config = load_config()
    if not config:
        return "UTC"
    timezone_name = config.get("timezone", "UTC")
    # Validate
    try:
        ZoneInfo(timezone_name)
        return timezone_name
    except (KeyError, ValueError):
        return "UTC"


DEFAULT_LANGUAGE = "Korean"


def get_language() -> str:
    """Return the language from config.yaml.

    This is the single source of truth for response language across all of abyss.
    Falls back to 'Korean' if config is not found or language is not set.
    """
    config = load_config()
    if not config:
        return DEFAULT_LANGUAGE
    return config.get("language", DEFAULT_LANGUAGE)


def get_elevenlabs_api_key() -> str:
    """Return the ElevenLabs API key from config.yaml, falling back to env var."""
    config = load_config()
    if config:
        key = config.get("elevenlabs_api_key", "")
        if key:
            return str(key)
    return os.environ.get("ELEVENLABS_API_KEY", "")
